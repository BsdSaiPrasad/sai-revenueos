"""Acceptance scenarios for P1.5 deterministic synthetic GTM data."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_authority import AuthorityPolicy  # noqa: E402
from sai_revenueos_identity import IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceEvent, SourceStore, standardize_event  # noqa: E402
from sai_revenueos_synthetic import (  # noqa: E402
    GenerationConfig,
    generate_dataset,
    validate_dataset,
    write_dataset,
)


class SyntheticDataTests(unittest.TestCase):
    """Protect reproducibility, relationships, quality scenarios, and scale."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = generate_dataset(GenerationConfig(company_count=25, seed=42))

    def test_01_presets_and_custom_sizes_use_valid_configuration(self) -> None:
        """Documented presets and a custom size are accepted; incomplete ecosystems are rejected."""
        for size in (25, 250, 2500, 37):
            self.assertEqual(size, GenerationConfig(company_count=size, seed=9).company_count)
        for size in (0, 1, 2, 100_001):
            with self.assertRaises(ValueError):
                GenerationConfig(company_count=size)
        with self.assertRaises(ValueError):
            GenerationConfig(company_count=25, seed=True)

    def test_02_same_parameters_produce_identical_dataset(self) -> None:
        """The same size and seed reproduce every value and the same fingerprint."""
        repeated = generate_dataset(GenerationConfig(company_count=25, seed=42))
        self.assertEqual(self.dataset.as_document(), repeated.as_document())
        self.assertEqual(self.dataset.fingerprint(), repeated.fingerprint())

    def test_03_different_seed_changes_data_without_changing_shape(self) -> None:
        """A new seed changes generated identities and names while preserving configured counts."""
        changed = generate_dataset(GenerationConfig(company_count=25, seed=43))
        self.assertNotEqual(self.dataset.fingerprint(), changed.fingerprint())
        self.assertEqual(self.dataset.counts(), changed.counts())

    def test_04_ecosystem_relationships_reference_known_entities(self) -> None:
        """Companies, people, opportunities, activities, and hierarchy rows remain connected."""
        report = validate_dataset(self.dataset)
        self.assertTrue(report.valid, report.errors)
        accounts = {row["account_id"] for row in self.dataset.companies}
        globex, diagnostics, northstar = self.dataset.companies[:3]
        pairs = {
            (row["parent_account_id"], row["child_account_id"], row["relationship_type"])
            for row in self.dataset.account_relationships
        }
        self.assertIn((globex["account_id"], diagnostics["account_id"], "subsidiary"), pairs)
        self.assertIn((globex["account_id"], northstar["account_id"], "acquired_company"), pairs)
        self.assertEqual(accounts, {row["primary_account_id"] for row in self.dataset.opportunities})
        self.assertEqual(50, len(self.dataset.people))
        self.assertEqual(50, len(self.dataset.activities))

    def test_05_every_source_event_uses_existing_p13_contracts(self) -> None:
        """Generated Salesforce and HubSpot envelopes validate and standardize without new objects."""
        seen = set()
        for document in self.dataset.source_events:
            event = SourceEvent.from_dict(document)
            standard = standardize_event(event)
            self.assertEqual(event.source_object_id, standard["source_object_id"])
            seen.add((event.source_system, event.source_object_type))
        self.assertEqual(
            {
                ("salesforce", "Account"), ("salesforce", "Lead"),
                ("salesforce", "Contact"), ("salesforce", "Opportunity"),
                ("hubspot", "Company"), ("hubspot", "Contact"), ("hubspot", "Deal"),
            },
            seen,
        )

    def test_06_history_preserves_rebrand_job_change_and_late_event(self) -> None:
        """Historical names and employment stay effective-dated while late input remains explicit."""
        northstar_id = self.dataset.companies[2]["account_id"]
        northstar_names = [
            row for row in self.dataset.account_name_history if row["account_id"] == northstar_id
        ]
        self.assertEqual(["Northstar Research", "Northstar Labs"], [row["name"] for row in northstar_names])
        sarah_history = [
            row for row in self.dataset.employment_history
            if row["person_id"] == self.dataset.people[0]["person_id"]
        ]
        self.assertEqual(2, len(sarah_history))
        self.assertEqual(self.dataset.companies[2]["account_id"], sarah_history[0]["account_id"])
        globex_events = [
            row for row in self.dataset.salesforce_events
            if row["source"]["object_type"] == "Account"
            and row["source"]["object_id"] == self.dataset.companies[0]["salesforce_account_id"]
        ]
        positions = {row["event_id"]: index for index, row in enumerate(globex_events)}
        self.assertLess(positions["p15-sf-account-000000-v2"], positions["p15-sf-account-000000-late"])
        self.assertGreater(
            next(row for row in globex_events if row["event_id"].endswith("v2"))["timestamps"]["source_updated_at"],
            next(row for row in globex_events if row["event_id"].endswith("late"))["timestamps"]["source_updated_at"],
        )

    def test_07_manifest_exposes_every_required_quality_problem(self) -> None:
        """Intentional duplicates, gaps, conflicts, ambiguity, and history are discoverable."""
        issue_types = set(self.dataset.manifest()["quality_issue_counts"])
        self.assertTrue({
            "duplicate_record", "duplicate_event", "missing_optional_field",
            "conflicting_information", "acquisition", "company_rebrand",
            "employee_job_change", "ambiguous_identity_match", "late_out_of_order_event",
        }.issubset(issue_types))
        self.assertTrue(all(item["expected_outcome"] for item in self.dataset.quality_issues))
        self.assertTrue(all(
            outcome["automatic_merge"] is False
            for outcome in self.dataset.expected_identity_outcomes
        ))

    def test_08_generated_unknown_identities_are_not_automatically_merged(self) -> None:
        """P1.2 keeps matching Globex source records unresolved until explicit review."""
        sf = next(row for row in self.dataset.salesforce_events if row["event_id"] == "p15-sf-account-000000-v1")
        hs = next(row for row in self.dataset.hubspot_events if row["event_id"] == "p15-hs-company-000000-v1")
        with IdentityStore() as identity, SourceStore() as sources:
            results = [
                sources.process_event(SourceEvent.from_dict(document), identity)
                for document in (sf, hs)
            ]
            self.assertEqual(2, identity.count("source_record"))
            for result in results:
                self.assertEqual("unresolved", identity.resolution_case_for_source(result.source_record_id)["status"])
                self.assertIsNone(identity.active_mapping_for_source(result.source_record_id))

    def test_09_conflict_expectations_reuse_p14_field_authority(self) -> None:
        """The manifest cites existing Salesforce ownership instead of inventing a new rule."""
        policy = AuthorityPolicy()
        manifest = self.dataset.manifest()
        self.assertEqual(
            frozenset({"salesforce"}),
            policy.field("Account", "lifecycle_status").authoritative_sources,
        )
        self.assertEqual(
            "preserve_both_and_open_review",
            manifest["authority_expectations"]["Account.lifecycle_status"]["expected_action"],
        )

    def test_10_writer_emits_repeatable_json_jsonl_csv_and_manifest(self) -> None:
        """Readable and machine-readable files reproduce byte-for-byte across directories."""
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_paths = write_dataset(self.dataset, Path(first))
            second_paths = write_dataset(self.dataset, Path(second))
            self.assertEqual(11, len(first_paths))
            for key in first_paths:
                self.assertEqual(first_paths[key].read_bytes(), second_paths[key].read_bytes())
            manifest = json.loads(first_paths["manifest"].read_text(encoding="utf-8"))
            self.assertEqual(self.dataset.fingerprint(), manifest["dataset_fingerprint_sha256"])
            self.assertEqual(
                len(self.dataset.salesforce_events),
                len(first_paths["salesforce_jsonl"].read_text(encoding="utf-8").splitlines()),
            )

    def test_11_all_documented_scales_generate_and_validate(self) -> None:
        """The 25, 250, and 2,500 company presets remain practical and contract-valid."""
        for size in (25, 250, 2500):
            dataset = self.dataset if size == 25 else generate_dataset(
                GenerationConfig(company_count=size, seed=42)
            )
            report = validate_dataset(dataset)
            self.assertTrue(report.valid, report.errors)
            self.assertEqual(size, dataset.counts()["companies"])
            self.assertEqual(size * 2, dataset.counts()["people"])
            self.assertEqual(size * 2, dataset.counts()["activities"])


if __name__ == "__main__":
    unittest.main()
