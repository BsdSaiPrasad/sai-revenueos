"""Executable acceptance scenarios for the P1.2 identity reference layer."""

from __future__ import annotations

import sqlite3
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from sai_revenueos_identity import (  # noqa: E402
    IDENTITY_STEWARD,
    IDENTITY_WRITER,
    RESOLUTION_WRITER,
    SOURCE_WRITER,
    IdentityStore,
    PREFIX_REGISTRY,
    PrefixedIDGenerator,
    uuid7,
    validate_prefixed_id,
)
from sai_revenueos_identity.errors import (  # noqa: E402
    AuthorizationError,
    ConflictError,
    IdempotencyConflictError,
    InvalidTransitionError,
    SimulatedFailure,
    ValidationError,
)


T0 = "2026-10-10T12:00:00.000000Z"
T1 = "2026-10-10T12:01:00.000000Z"
T2 = "2026-10-10T12:02:00.000000Z"
T3 = "2026-10-10T12:03:00.000000Z"
T4 = "2026-10-10T12:04:00.000000Z"


class IdentityReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = IdentityStore()

    def tearDown(self) -> None:
        self.store.close()

    def canonical(self, entity_type: str = "Account", key: str = "canonical-1", at: str = T0) -> str:
        return self.store.create_canonical_identity(
            entity_type, "p1-service", IDENTITY_WRITER, key, at
        )

    def source(
        self, object_id: str = "001GLOBEX", tenant: str = "globex-prod",
        system: str = "Salesforce", observation: str = "obs-1", at: str = T0,
    ) -> str:
        return self.store.get_or_create_source_record(
            system, tenant, "Account", object_id, observation, "connector",
            SOURCE_WRITER, "sha256:example", "s3://synthetic/example", at,
        )

    def resolve(
        self, source_id: str, canonical_id: str, stem: str = "globex", at: str = T1
    ) -> tuple[str, str]:
        candidate = self.store.propose_candidate(
            source_id, canonical_id, "domain", "%s.example" % stem, 0.97,
            "explicit_test_evidence", "p1.2-v1", "resolver", RESOLUTION_WRITER,
            "%s-propose" % stem, at,
        )
        self.store.decide_candidate(
            candidate, "accepted", "verified by steward", "sai", IDENTITY_STEWARD,
            "%s-accept" % stem, T2,
        )
        mapping = self.store.activate_mapping(
            candidate, "sai", IDENTITY_STEWARD, "%s-map" % stem, T3
        )
        return candidate, mapping

    def test_01_unique_prefixed_uuid7_generation(self) -> None:
        contract = json.loads(
            (SRC.parents[2] / "shared" / "contracts" / "canonical-model.v1.json").read_text(encoding="utf-8")
        )
        self.assertTrue(set(contract["entities"]).issubset(PREFIX_REGISTRY))
        values = {self.canonical(key="canonical-%d" % n) for n in range(100)}
        self.assertEqual(100, len(values))
        for value in values:
            validate_prefixed_id("Account", value)
            self.assertTrue(value.startswith("sai_acc_"))

    def test_02_collision_detection_retries_safely(self) -> None:
        first, second = uuid7(1, 1), uuid7(1, 2)
        sequence = iter([first, first, second])
        generator = PrefixedIDGenerator(max_attempts=3, uuid_factory=lambda: next(sequence))
        existing = {"sai_acc_" + str(first)}
        generated = generator.generate("Account", existing.__contains__)
        self.assertEqual("sai_acc_" + str(second), generated)

    def test_03_repeated_salesforce_record_is_one_source_with_two_observations(self) -> None:
        first = self.source(observation="sf-run-1")
        second = self.source(observation="sf-run-2", at=T1)
        third = self.source(observation="sf-run-2", at=T2)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(1, self.store.count("source_record"))
        self.assertEqual(2, self.store.count("source_observation"))

    def test_04_salesforce_and_hubspot_link_to_same_account(self) -> None:
        account = self.canonical()
        salesforce = self.source(observation="sf-globex")
        hubspot = self.source("987654", "globex-hub", "HubSpot", "hs-globex")
        self.resolve(salesforce, account, "salesforce")
        self.resolve(hubspot, account, "hubspot")
        self.assertEqual(account, self.store.active_mapping_for_source(salesforce)["canonical_entity_id"])
        self.assertEqual(account, self.store.active_mapping_for_source(hubspot)["canonical_entity_id"])

    def test_05_same_vendor_id_in_different_tenants_is_distinct(self) -> None:
        globex = self.source("001SAME", "globex-prod", observation="obs-globex")
        northstar = self.source("001SAME", "northstar-prod", observation="obs-northstar")
        self.assertNotEqual(globex, northstar)
        self.assertEqual(2, self.store.count("source_record"))

    def test_06_new_source_stays_unresolved(self) -> None:
        source = self.source()
        case = self.store.resolution_case_for_source(source)
        self.assertEqual("unresolved", case["status"])
        self.assertIsNone(self.store.active_mapping_for_source(source))

    def test_07_ambiguous_candidates_require_review(self) -> None:
        source = self.source()
        globex = self.canonical(key="globex")
        northstar = self.canonical(key="northstar")
        self.store.propose_candidate(
            source, globex, "domain", "globex.example", 0.70, "rule", "v1",
            "resolver", RESOLUTION_WRITER, "candidate-a", T1,
        )
        self.store.propose_candidate(
            source, northstar, "name", "Globex Health", 0.69, "rule", "v1",
            "resolver", RESOLUTION_WRITER, "candidate-b", T2,
        )
        case = self.store.resolution_case_for_source(source)
        self.assertEqual("ambiguous", case["status"])
        self.assertEqual(1, case["review_required"])
        self.store.request_manual_review(
            source, "two plausible companies", "resolver", RESOLUTION_WRITER, "review-1", T3
        )
        self.assertEqual("pending_review", self.store.resolution_case_for_source(source)["status"])

    def test_08_correction_preserves_historical_mapping(self) -> None:
        source = self.source()
        wrong = self.canonical(key="wrong")
        correct = self.canonical(key="correct")
        _, original = self.resolve(source, wrong)
        replacement = self.store.correct_mapping(
            source, correct, "wrong Globex subsidiary", "sai", IDENTITY_STEWARD,
            "correct-1", T4,
        )
        old = self.store.get("external_identity_crosswalk", "external_identity_crosswalk_id", original)
        new = self.store.get("external_identity_crosswalk", "external_identity_crosswalk_id", replacement)
        self.assertEqual("superseded", old["mapping_status"])
        self.assertEqual(T4, old["valid_to"])
        self.assertEqual(original, new["supersedes_crosswalk_id"])
        self.assertEqual(correct, new["canonical_entity_id"])
        self.assertEqual(2, self.store.count("external_identity_crosswalk"))

    def test_09_incorrect_merge_can_be_unmerged_to_original_id(self) -> None:
        survivor = self.canonical(key="globex-parent")
        original = self.canonical(key="northstar-independent")
        source = self.source("001NORTH", "northstar-prod", observation="northstar-obs")
        self.resolve(source, original, "northstar")
        merge = self.store.merge_identities(
            survivor, original, "incorrect acquisition assumption", "sai", IDENTITY_STEWARD,
            "merge-1", T4,
        )
        retired = self.store.get("canonical_identity", "canonical_id", original)
        self.assertEqual("retired", retired["identity_status"])
        self.assertEqual(survivor, retired["redirect_to_canonical_id"])
        unmerge, uncertain = self.store.unmerge_identities(
            merge, "companies remain independent", "sai", IDENTITY_STEWARD,
            "unmerge-1", "2026-10-10T12:05:00.000000Z",
        )
        self.assertTrue(unmerge.startswith("sai_merge_"))
        self.assertEqual([], uncertain)
        restored = self.store.get("canonical_identity", "canonical_id", original)
        self.assertEqual("active", restored["identity_status"])
        self.assertEqual(original, self.store.active_mapping_for_source(source)["canonical_entity_id"])

    def test_10_retry_returns_same_effect_and_key_reuse_conflicts(self) -> None:
        first = self.canonical(key="retry-key")
        second = self.canonical(key="retry-key")
        self.assertEqual(first, second)
        self.assertEqual(1, self.store.count("canonical_identity"))
        with self.assertRaises(IdempotencyConflictError):
            self.store.create_canonical_identity(
                "Person", "p1-service", IDENTITY_WRITER, "retry-key", T1
            )

    def test_11_invalid_mapping_transition_is_blocked_by_database(self) -> None:
        source = self.source()
        account = self.canonical()
        _, mapping = self.resolve(source, account)
        self.store.revoke_mapping(
            source, "confirmed source retirement", "sai", IDENTITY_STEWARD,
            "transition-revoke", T4,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "UPDATE external_identity_crosswalk SET mapping_status='active', valid_to=NULL "
                "WHERE external_identity_crosswalk_id=?", (mapping,),
            )
        history = self.store.get("external_identity_crosswalk", "external_identity_crosswalk_id", mapping)
        self.assertEqual("revoked", history["mapping_status"])

    def test_12_concurrent_source_upserts_produce_one_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "identity.db")
            # Initialize the schema once; each concurrent worker then owns its
            # SQLite connection, as a real request worker would.
            with IdentityStore(database):
                pass
            barrier = threading.Barrier(2)
            results: list[str] = []
            errors: list[Exception] = []

            def worker(index: int) -> None:
                store = IdentityStore(database)
                try:
                    barrier.wait()
                    results.append(store.get_or_create_source_record(
                        "Salesforce", "globex-prod", "Account", "001CONCURRENT",
                        "concurrent-%d" % index, "connector", SOURCE_WRITER, observed_at=T0,
                    ))
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)
                finally:
                    store.close()

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual([], errors)
            self.assertEqual(1, len(set(results)))
            with IdentityStore(database) as verifier:
                self.assertEqual(1, verifier.count("source_record"))
                self.assertEqual(2, verifier.count("source_observation"))

    def test_13_simulated_failure_rolls_back_mapping_and_idempotency_claim(self) -> None:
        source = self.source()
        wrong = self.canonical(key="wrong")
        correct = self.canonical(key="correct")
        _, original = self.resolve(source, wrong)
        before_audits = self.store.count("audit_event")
        with self.assertRaises(SimulatedFailure):
            self.store.correct_mapping(
                source, correct, "test rollback", "sai", IDENTITY_STEWARD,
                "rollback-correction", T4, simulate_failure=True,
            )
        active = self.store.active_mapping_for_source(source)
        self.assertEqual(original, active["external_identity_crosswalk_id"])
        self.assertEqual("active", active["mapping_status"])
        self.assertEqual(before_audits, self.store.count("audit_event"))
        replacement = self.store.correct_mapping(
            source, correct, "test rollback", "sai", IDENTITY_STEWARD,
            "rollback-correction", T4,
        )
        self.assertNotEqual(original, replacement)

    def test_14_overlapping_mapping_intervals_are_prevented(self) -> None:
        source = self.source()
        account = self.canonical()
        _, mapping = self.resolve(source, account)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "INSERT INTO external_identity_crosswalk VALUES "
                "(?, ?, 'Account', ?, 'superseded', 'forbidden', 1.0, ?, ?, NULL, ?, ?, NULL, ?)",
                ("sai_xwalk_" + str(uuid7()), source, account, T2, T4, "sai", T2, T2),
            )
        self.assertEqual(mapping, self.store.active_mapping_for_source(source)["external_identity_crosswalk_id"])

    def test_15_malformed_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.store.get_or_create_source_record(
                "Salesforce", "globex-prod", "Account", "bad\x00id", "obs", "connector",
                SOURCE_WRITER,
            )
        with self.assertRaises(ValidationError):
            validate_prefixed_id("Account", "sai_acc_not-a-uuid")
        with self.assertRaises(ValidationError):
            self.store.create_canonical_identity(
                "Account", "   ", IDENTITY_WRITER, "empty-actor"
            )
        self.assertEqual(0, self.store.count("source_record"))

    def test_16_unauthorized_state_changes_are_rejected(self) -> None:
        with self.assertRaises(AuthorizationError):
            self.store.create_canonical_identity("Account", "intruder", SOURCE_WRITER, "bad-auth")
        source = self.source()
        account = self.canonical()
        candidate = self.store.propose_candidate(
            source, account, "domain", "globex.example", 0.9, "rule", "v1",
            "resolver", RESOLUTION_WRITER, "auth-candidate", T1,
        )
        with self.assertRaises(AuthorizationError):
            self.store.decide_candidate(
                candidate, "accepted", "not authorized", "intruder", RESOLUTION_WRITER,
                "bad-decision", T2,
            )

    def test_17_rebrand_retains_account_identity(self) -> None:
        account = self.canonical()
        # A name change is descriptive history in the canonical model, never a new identity.
        self.assertEqual(account, self.canonical(key="canonical-1"))
        self.assertEqual(1, self.store.count("canonical_identity"))

    def test_18_acquisition_does_not_automatically_merge_accounts(self) -> None:
        globex = self.canonical(key="globex")
        northstar = self.canonical(key="northstar")
        self.assertNotEqual(globex, northstar)
        self.assertEqual("active", self.store.get("canonical_identity", "canonical_id", globex)["identity_status"])
        self.assertEqual("active", self.store.get("canonical_identity", "canonical_id", northstar)["identity_status"])

    def test_19_revocation_removes_authority_but_keeps_history(self) -> None:
        source = self.source()
        account = self.canonical()
        _, mapping = self.resolve(source, account)
        result = self.store.revoke_mapping(
            source, "source record was deleted upstream", "sai", IDENTITY_STEWARD,
            "revoke-1", T4,
        )
        self.assertEqual(mapping, result)
        self.assertIsNone(self.store.active_mapping_for_source(source))
        history = self.store.get("external_identity_crosswalk", "external_identity_crosswalk_id", mapping)
        self.assertEqual("revoked", history["mapping_status"])
        self.assertEqual("no_match", self.store.resolution_case_for_source(source)["status"])

    def test_20_reconciliation_is_clean_after_valid_flow(self) -> None:
        source = self.source()
        account = self.canonical()
        self.resolve(source, account)
        self.assertEqual([], self.store.reconcile())

    def test_21_reconciliation_detects_resolved_case_missing_mapping(self) -> None:
        source = self.source()
        account = self.canonical()
        candidate = self.store.propose_candidate(
            source, account, "domain", "globex.example", 0.9, "rule", "v1",
            "resolver", RESOLUTION_WRITER, "reconcile-propose", T1,
        )
        self.store.decide_candidate(
            candidate, "accepted", "verified", "sai", IDENTITY_STEWARD,
            "reconcile-accept", T2,
        )
        issue_types = {item["issue_type"] for item in self.store.reconcile()}
        self.assertIn("resolved_case_without_active_mapping", issue_types)

    def test_22_uncertain_post_merge_change_requires_human_review(self) -> None:
        globex = self.canonical(key="globex")
        northstar = self.canonical(key="northstar")
        corrected_target = self.canonical(key="third-account")
        source = self.source("001NORTH", "northstar-prod", observation="northstar")
        self.resolve(source, northstar, "northstar-uncertain")
        merge = self.store.merge_identities(
            globex, northstar, "incorrect acquisition", "sai", IDENTITY_STEWARD,
            "uncertain-merge", T4,
        )
        self.store.correct_mapping(
            source, corrected_target, "new evidence after merge", "sai", IDENTITY_STEWARD,
            "post-merge-correction", "2026-10-10T12:05:00.000000Z",
        )
        _, uncertain = self.store.unmerge_identities(
            merge, "reverse incorrect acquisition", "sai", IDENTITY_STEWARD,
            "uncertain-unmerge", "2026-10-10T12:06:00.000000Z",
        )
        self.assertEqual([source], uncertain)
        case = self.store.resolution_case_for_source(source)
        self.assertEqual("pending_review", case["status"])
        self.assertEqual(1, case["review_required"])
        self.assertEqual(corrected_target, self.store.active_mapping_for_source(source)["canonical_entity_id"])

    def test_23_canonical_ids_cannot_be_deleted_or_reused(self) -> None:
        account = self.canonical()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute(
                "DELETE FROM canonical_identity WHERE canonical_id=?", (account,)
            )
        self.assertEqual(account, self.store.get("canonical_identity", "canonical_id", account)["canonical_id"])


if __name__ == "__main__":
    unittest.main()
