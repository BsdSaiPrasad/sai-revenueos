"""Acceptance scenarios for P1.8 identity resolution and survivorship."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_authority import AuthorityStore  # noqa: E402
from sai_revenueos_identity import (  # noqa: E402
    IDENTITY_STEWARD,
    IDENTITY_WRITER,
    RESOLUTION_WRITER,
    SOURCE_WRITER,
    IdentityStore,
)
from sai_revenueos_resolution import (  # noqa: E402
    ResolutionAuthorizationError,
    ResolutionConflictError,
    ResolutionPolicy,
    ResolutionService,
    ResolutionStore,
    SimulatedResolutionFailure,
    SnowflakeStagingReader,
    StagedIdentityRecord,
)


T0 = "2026-10-13T12:00:00.000000Z"


class _Cursor:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.description = [(name,) for name in rows[0]] if rows else []
        self.sql = ""

    def execute(self, sql: str) -> None:
        self.sql = sql

    def fetchall(self):
        return [tuple(row.values()) for row in self.rows]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, batches: List[List[Dict[str, Any]]]) -> None:
        self.batches = list(batches)
        self.cursors: List[_Cursor] = []

    def cursor(self) -> _Cursor:
        cursor = _Cursor(self.batches.pop(0))
        self.cursors.append(cursor)
        return cursor


class IdentityResolutionTests(unittest.TestCase):
    """Protect deterministic evidence, review gates, recovery, and P1.7 input."""

    def setUp(self) -> None:
        self.identity = IdentityStore()
        self.resolution = ResolutionStore()
        self.authority = AuthorityStore()
        self.service = ResolutionService(self.identity, self.resolution)
        self.records: List[StagedIdentityRecord] = []

    def tearDown(self) -> None:
        self.authority.close()
        self.resolution.close()
        self.identity.close()

    def source(
        self,
        system: str,
        object_type: str,
        object_id: str,
        event_id: str,
        entity_type: str = "Account",
        name: str = "Globex Health",
        domain: str = "globex.example",
        email: str = "",
        raw_payload: Optional[Dict[str, Any]] = None,
    ) -> StagedIdentityRecord:
        source_record_id = self.identity.get_or_create_source_record(
            system, "tenant-1", object_type, object_id, event_id,
            "p1.8-test", SOURCE_WRITER, event_id, "snowflake://%s" % event_id, T0,
        )
        record = StagedIdentityRecord(
            event_id=event_id,
            source_record_id=source_record_id,
            source_system=system,
            source_tenant="tenant-1",
            source_object_type=object_type,
            source_object_id=object_id,
            entity_type=entity_type,
            name=name or None,
            domain=domain or None,
            email=email or None,
            country="United States" if entity_type == "Account" else None,
            source_updated_at=T0,
            observed_at=T0,
            trace_id="trace-%s" % event_id,
            payload_sha256="a" * 64,
            raw_payload=raw_payload or {},
            staging_model="STG_CRM_COMPANIES" if entity_type == "Account" else "STG_CRM_PEOPLE",
        )
        self.records.append(record)
        return record

    def canonical(self, entity_type: str, key: str) -> str:
        return self.identity.create_canonical_identity(
            entity_type, "p1.8-test", IDENTITY_WRITER, "canonical-%s" % key, T0
        )

    def seed_mapping(self, record: StagedIdentityRecord, canonical_id: str, key: str) -> str:
        candidate = self.identity.propose_candidate(
            record.source_record_id, canonical_id, "manual_seed", "test://%s" % key,
            1.0, "manual", "seed-v1", "steward", RESOLUTION_WRITER,
            "seed-propose-%s" % key, T0,
        )
        self.identity.decide_candidate(
            candidate, "accepted", "known synthetic fixture", "steward",
            IDENTITY_STEWARD, "seed-decide-%s" % key, T0,
        )
        return self.identity.activate_mapping(
            candidate, "steward", IDENTITY_STEWARD, "seed-map-%s" % key, T0
        )

    def globex_pair(self):
        salesforce = self.source(
            "salesforce", "Account", "001GLOBEX", "evt-sf-globex",
            raw_payload={"Lifecycle_Status__c": "customer"},
        )
        hubspot = self.source(
            "hubspot", "Company", "501", "evt-hs-globex",
            name="Globex Health, Inc.", domain="https://www.globex.example/about",
            raw_payload={"properties": {"lifecyclestage": "marketingqualifiedlead"}},
        )
        account_id = self.canonical("Account", "globex")
        self.seed_mapping(salesforce, account_id, "globex-sf")
        return salesforce, hubspot, account_id

    def test_01_policy_requires_human_review_and_reuses_p14(self) -> None:
        """The versioned policy cannot auto-activate, auto-merge, or replace P1.4."""
        policy = ResolutionPolicy()
        self.assertEqual("1.0.0", policy.contract_version)
        self.assertTrue(policy.human_approval_required)
        self.assertFalse(policy.automatic_merge)
        self.assertEqual("STG_CRM_COMPANIES", policy.input_models["Account"])
        self.assertEqual("STG_CRM_PEOPLE", policy.input_models["Person"])

    def test_02_strong_account_match_still_requires_human_approval(self) -> None:
        """A clear Globex candidate remains non-authoritative until a steward acts."""
        _, hubspot, account_id = self.globex_pair()
        result = self.service.resolve(hubspot, self.records)
        case = self.identity.resolution_case_for_source(hubspot.source_record_id)
        self.assertEqual("candidate", result.outcome)
        self.assertEqual(account_id, result.candidates[0].canonical_entity_id)
        self.assertGreaterEqual(result.candidates[0].score, 0.55)
        self.assertEqual("pending_review", case["status"])
        self.assertIsNone(self.identity.active_mapping_for_source(hubspot.source_record_id))

    def test_03_approval_activates_crosswalk_and_publishes_p19_boundary(self) -> None:
        """Only steward approval creates the active mapping exported to P1.9."""
        _, hubspot, account_id = self.globex_pair()
        result = self.service.resolve(hubspot, self.records)
        review = self.resolution.get_review(result.review_id)
        approved = self.service.approve(
            result.review_id, review["candidate_evidence_ids"][0], "sarah-kim",
            IDENTITY_STEWARD, "verified Globex source evidence",
        )
        mapping = self.identity.active_mapping_for_source(hubspot.source_record_id)
        output = self.service.approved_mapping_output("2026-10-13T12:30:00Z")
        self.assertEqual(account_id, mapping["canonical_entity_id"])
        self.assertEqual(approved.crosswalk_id, mapping["external_identity_crosswalk_id"])
        self.assertEqual("identity-resolution-output", output["contract_name"])
        self.assertTrue(any(row["source_record_id"] == hubspot.source_record_id for row in output["mappings"]))

    def test_04_duplicate_processing_is_idempotent(self) -> None:
        """Reprocessing the same staged context returns one run, candidate, and review."""
        _, hubspot, _ = self.globex_pair()
        first = self.service.resolve(hubspot, self.records)
        repeated = self.service.resolve(hubspot, self.records)
        self.assertFalse(first.replayed)
        self.assertTrue(repeated.replayed)
        self.assertEqual(first.run_id, repeated.run_id)
        self.assertEqual(1, self.resolution.count("resolution_run"))
        self.assertEqual(1, self.resolution.count("match_candidate_result"))
        self.assertEqual(1, self.resolution.count("identity_review_work_item"))

    def test_05_two_plausible_accounts_are_ambiguous(self) -> None:
        """A duplicate Globex profile produces two candidates and no active mapping."""
        _, target, _ = self.globex_pair()
        duplicate = self.source(
            "salesforce", "Account", "001GLOBEX2", "evt-sf-globex-duplicate",
            name="Globex Healthcare", domain="globex.example",
        )
        duplicate_id = self.canonical("Account", "globex-duplicate")
        self.seed_mapping(duplicate, duplicate_id, "globex-duplicate")
        result = self.service.resolve(target, self.records)
        self.assertEqual("ambiguous", result.outcome)
        self.assertEqual(2, len(result.candidates))
        self.assertEqual("pending_review", self.identity.resolution_case_for_source(target.source_record_id)["status"])
        self.assertIsNone(self.identity.active_mapping_for_source(target.source_record_id))

    def test_06_missing_identity_evidence_opens_review_without_fabricating_match(self) -> None:
        """A record without useful fields stays unmapped and visible for review."""
        target = self.source(
            "hubspot", "Company", "999", "evt-hs-missing", name="", domain=""
        )
        result = self.service.resolve(target, self.records)
        self.assertEqual("pending_review", result.outcome)
        self.assertEqual(0, len(result.candidates))
        self.assertIsNotNone(result.review_id)
        self.assertIsNone(self.identity.active_mapping_for_source(target.source_record_id))

    def test_07_unauthorized_approval_is_rejected(self) -> None:
        """A source processor cannot turn a candidate into authoritative truth."""
        _, target, _ = self.globex_pair()
        result = self.service.resolve(target, self.records)
        candidate = self.resolution.get_review(result.review_id)["candidate_evidence_ids"][0]
        with self.assertRaises(ResolutionAuthorizationError):
            self.service.approve(
                result.review_id, candidate, "connector", RESOLUTION_WRITER, "not authorized"
            )
        self.assertIsNone(self.identity.active_mapping_for_source(target.source_record_id))

    def test_08_new_evidence_makes_the_older_review_stale(self) -> None:
        """A delayed decision cannot overwrite a newer ambiguous resolution version."""
        _, target, _ = self.globex_pair()
        first = self.service.resolve(target, self.records)
        duplicate = self.source(
            "salesforce", "Account", "001NEW", "evt-new-context",
            name="Globex Health", domain="globex.example",
        )
        second_id = self.canonical("Account", "new-context")
        self.seed_mapping(duplicate, second_id, "new-context")
        second = self.service.resolve(target, self.records)
        self.assertEqual("ambiguous", second.outcome)
        self.assertEqual("stale", self.resolution.get_review(first.review_id)["status"])
        with self.assertRaises(ResolutionConflictError):
            self.service.approve(
                first.review_id,
                self.resolution.get_review(first.review_id)["candidate_evidence_ids"][0],
                "sarah-kim", IDENTITY_STEWARD, "late browser decision",
            )

    def test_09_resolution_and_approval_recover_after_simulated_failures(self) -> None:
        """Deterministic keys recover without duplicate evidence or crosswalks."""
        _, target, _ = self.globex_pair()
        with self.assertRaises(SimulatedResolutionFailure):
            self.service.resolve(target, self.records, simulate_failure=True)
        result = self.service.resolve(target, self.records)
        candidate = self.resolution.get_review(result.review_id)["candidate_evidence_ids"][0]
        with self.assertRaises(SimulatedResolutionFailure):
            self.service.approve(
                result.review_id, candidate, "sarah-kim", IDENTITY_STEWARD,
                "verified after retry", simulate_failure_after_decision=True,
            )
        approval = self.service.approve(
            result.review_id, candidate, "sarah-kim", IDENTITY_STEWARD,
            "verified after retry",
        )
        self.assertTrue(approval.replayed)
        self.assertEqual(2, self.identity.count("external_identity_crosswalk"))

    def test_10_person_email_match_is_explainable_and_manual(self) -> None:
        """Sarah Kim's matching email proposes one Person without activating it."""
        salesforce = self.source(
            "salesforce", "Contact", "003SARAH", "evt-sf-sarah", entity_type="Person",
            name="Sarah Kim", domain="", email="sarah.kim@globex.example",
        )
        hubspot = self.source(
            "hubspot", "Contact", "801", "evt-hs-sarah", entity_type="Person",
            name="Sarah Kim", domain="", email="SARAH.KIM@globex.example",
        )
        person_id = self.canonical("Person", "sarah")
        self.seed_mapping(salesforce, person_id, "sarah-sf")
        result = self.service.resolve(hubspot, self.records)
        self.assertEqual(person_id, result.candidates[0].canonical_entity_id)
        self.assertTrue(result.candidates[0].features["exact_email"])
        self.assertIsNone(self.identity.active_mapping_for_source(hubspot.source_record_id))

    def test_11_survivorship_uses_p14_and_preserves_conflict(self) -> None:
        """Salesforce wins lifecycle authority while HubSpot disagreement is retained."""
        _, hubspot, account_id = self.globex_pair()
        result = self.service.resolve(hubspot, self.records)
        candidate = self.resolution.get_review(result.review_id)["candidate_evidence_ids"][0]
        self.service.approve(
            result.review_id, candidate, "sarah-kim", IDENTITY_STEWARD, "verified Globex"
        )
        outcomes = self.service.apply_survivorship(account_id, self.records, self.authority)
        current = self.authority.current_value("Account", account_id, "lifecycle_status")
        self.assertEqual(["applied", "denied"], [item.status for item in outcomes])
        self.assertEqual("customer", current["value"])
        self.assertEqual("salesforce", current["source_system"])
        self.assertEqual(1, self.authority.count("field_conflict"))

    def test_12_snowflake_reader_queries_both_p17_identity_views(self) -> None:
        """The production adapter reads P1.7 company and people views without writes."""
        company = {
            "EVENT_ID": "evt-company", "SOURCE_RECORD_ID": "sai_src_company",
            "SOURCE_SYSTEM": "salesforce", "SOURCE_TENANT": "tenant-1",
            "SOURCE_OBJECT_TYPE": "Account", "SOURCE_OBJECT_ID": "001",
            "ENTITY_TYPE": "Account", "NAME": "Globex Health", "DOMAIN": "globex.example",
            "EMAIL": None, "COUNTRY": "United States", "EMPLOYER_SOURCE_OBJECT_ID": None,
            "EMPLOYER_NAME": None, "JOB_TITLE": None, "EVENT_TYPE": "upsert",
            "IS_DELETED": False, "SOURCE_UPDATED_AT": T0, "OBSERVED_AT": T0,
            "TRACE_ID": "trace-company", "PAYLOAD_SHA256": "a" * 64,
            "RAW_PAYLOAD_JSON": {}, "STAGING_MODEL": "STG_CRM_COMPANIES",
        }
        person = dict(company)
        person.update({
            "EVENT_ID": "evt-person", "SOURCE_RECORD_ID": "sai_src_person",
            "SOURCE_OBJECT_TYPE": "Contact", "SOURCE_OBJECT_ID": "003",
            "ENTITY_TYPE": "Person", "NAME": "Sarah Kim", "DOMAIN": None,
            "EMAIL": "sarah@globex.example", "STAGING_MODEL": "STG_CRM_PEOPLE",
        })
        connection = _Connection([[company], [person]])
        records = SnowflakeStagingReader(connection).read_records()
        self.assertEqual(["Account", "Person"], [record.entity_type for record in records])
        self.assertIn("STG_CRM_COMPANIES", connection.cursors[0].sql)
        self.assertIn("STG_CRM_PEOPLE", connection.cursors[1].sql)

    def test_13_output_contract_excludes_unapproved_candidates(self) -> None:
        """Future P1.9 consumers see active crosswalks, never proposed candidates."""
        _, target, _ = self.globex_pair()
        self.service.resolve(target, self.records)
        output = self.service.approved_mapping_output(T0)
        ids = {row["source_record_id"] for row in output["mappings"]}
        self.assertNotIn(target.source_record_id, ids)
        contract = json.loads(
            (PROJECT / "contracts/identity-resolution-output.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual("identity-resolution-output", contract["properties"]["contract_name"]["const"])


if __name__ == "__main__":
    unittest.main()
