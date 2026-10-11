"""Executable acceptance scenarios for the P1.3 synthetic source model."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SRC = PROJECT / "src"
EXAMPLES = PROJECT / "examples" / "p13"
sys.path.insert(0, str(SRC))

from sai_revenueos_identity import (  # noqa: E402
    IDENTITY_STEWARD,
    IDENTITY_WRITER,
    RESOLUTION_WRITER,
    IdentityStore,
)
from sai_revenueos_identity.errors import ConflictError, SimulatedFailure, ValidationError  # noqa: E402
from sai_revenueos_sources import SourceContractRegistry, SourceEvent, SourceStore  # noqa: E402


def example(name: str) -> dict:
    """Load one checked-in synthetic event as a mutable test document."""
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class SourceModelTests(unittest.TestCase):
    """Protect raw history, tombstones, replay, and P1.2 integration."""

    def setUp(self) -> None:
        self.identity = IdentityStore()
        self.sources = SourceStore()

    def tearDown(self) -> None:
        self.sources.close()
        self.identity.close()

    def process(self, document: dict, simulate_failure: bool = False):
        """Validate and process one synthetic source event."""
        return self.sources.process_event(
            SourceEvent.from_dict(document), self.identity, simulate_failure=simulate_failure
        )

    def test_01_versioned_contracts_cover_essential_objects(self) -> None:
        """Both source contracts and the shared envelope/checkpoint contracts are version 1."""
        registry = SourceContractRegistry()
        self.assertEqual(
            {"Account", "Lead", "Contact", "Opportunity"},
            set(registry.contract("salesforce")["objects"]),
        )
        self.assertEqual(
            {"Company", "Contact", "Deal"},
            set(registry.contract("hubspot")["objects"]),
        )
        for name in ("source-event-envelope.v1.json", "source-checkpoint.v1.json"):
            contract = json.loads((PROJECT / "contracts" / name).read_text(encoding="utf-8"))
            self.assertIn("1.0.0", json.dumps(contract))

    def test_02_salesforce_raw_payload_precedes_standardization(self) -> None:
        """Unknown Salesforce fields remain raw while the current view stays compact."""
        document = example("globex-salesforce-account-created.json")
        result = self.process(document)
        raw = self.sources.get_event(document["event_id"])["raw_payload"]
        current = self.sources.current_state(result.source_record_id)["standardized_payload"]
        self.assertEqual("Enterprise", raw["Customer_Tier__c"])
        self.assertEqual(12500000, raw["AnnualRevenue"])
        self.assertNotIn("Customer_Tier__c", current)
        self.assertEqual("Globex Health", current["name"])

    def test_03_hubspot_nested_payload_is_preserved_and_standardized(self) -> None:
        """HubSpot history retains nested properties that are outside the essential subset."""
        document = example("globex-hubspot-company.json")
        result = self.process(document)
        history = self.sources.history_for_source(result.source_record_id)
        self.assertEqual("customer", history[0]["raw_payload"]["properties"]["lifecyclestage"])
        self.assertEqual("globex.example", history[0]["standardized_payload"]["domain"])
        self.assertNotIn("lifecyclestage", history[0]["standardized_payload"])

    def test_04_exact_duplicate_is_idempotent(self) -> None:
        """Replaying one event creates no duplicate history or P1.2 observation."""
        event = SourceEvent.from_dict(example("globex-salesforce-account-created.json"))
        first = self.sources.process_event(event, self.identity)
        second = self.sources.process_event(event, self.identity)
        self.assertEqual(first.source_record_id, second.source_record_id)
        self.assertTrue(second.replayed)
        self.assertEqual(1, self.sources.count("source_event"))
        self.assertEqual(1, self.sources.count("source_record_version"))
        self.assertEqual(1, self.identity.count("source_observation"))

    def test_05_update_appends_history_and_changes_current_state(self) -> None:
        """A newer update adds a version and becomes current without overwriting raw history."""
        first = self.process(example("globex-salesforce-account-created.json"))
        second = self.process(example("globex-salesforce-account-updated.json"))
        self.assertEqual(first.source_record_id, second.source_record_id)
        self.assertEqual(2, len(self.sources.history_for_source(first.source_record_id)))
        current = self.sources.current_state(first.source_record_id)
        self.assertEqual("evt-sf-account-001-v2", current["latest_event_id"])
        self.assertEqual("https://www.globex.example", current["standardized_payload"]["domain"])

    def test_06_deletion_creates_tombstone_without_deleting_canonical_identity(self) -> None:
        """A source deletion becomes current history but never removes a canonical Account."""
        canonical_id = self.identity.create_canonical_identity(
            "Account", "p1-service", IDENTITY_WRITER, "globex-canonical", "2026-10-11T13:59:00Z"
        )
        created = self.process(example("globex-salesforce-account-created.json"))
        candidate_id = self.identity.propose_candidate(
            created.source_record_id, canonical_id, "domain", "globex.example", 0.99,
            "explicit_test_evidence", "p1.3-v1", "resolver", RESOLUTION_WRITER,
            "globex-source-candidate", "2026-10-11T14:00:06Z",
        )
        self.identity.decide_candidate(
            candidate_id, "accepted", "verified synthetic fixture", "sai", IDENTITY_STEWARD,
            "globex-source-accepted", "2026-10-11T14:00:07Z",
        )
        self.identity.activate_mapping(
            candidate_id, "sai", IDENTITY_STEWARD, "globex-source-mapped", "2026-10-11T14:00:08Z"
        )
        self.process(example("globex-salesforce-account-deleted.json"))
        current = self.sources.current_state(created.source_record_id)
        self.assertEqual(1, current["is_deleted"])
        self.assertEqual(1, self.sources.history_for_source(created.source_record_id)[-1]["is_tombstone"])
        self.assertEqual("active", self.identity.get("canonical_identity", "canonical_id", canonical_id)["identity_status"])
        self.assertEqual(
            canonical_id,
            self.identity.active_mapping_for_source(created.source_record_id)["canonical_entity_id"],
        )

    def test_07_malformed_envelope_is_rejected_before_persistence(self) -> None:
        """An envelope missing tracing cannot enter raw history."""
        document = example("globex-salesforce-account-created.json")
        del document["tracing"]
        with self.assertRaises(ValidationError):
            SourceEvent.from_dict(document)
        self.assertEqual(0, self.sources.count("source_event"))

    def test_08_malformed_payload_is_preserved_but_not_checkpointed(self) -> None:
        """A valid envelope with a bad essential payload stays available for repair."""
        document = example("globex-salesforce-account-created.json")
        del document["payload"]["Name"]
        with self.assertRaises(ValidationError):
            self.process(document)
        stored = self.sources.get_event(document["event_id"])
        self.assertEqual("failed", stored["processing_status"])
        self.assertEqual("ValidationError", stored["last_error_type"])
        self.assertIn("AnnualRevenue", stored["raw_payload"])
        self.assertIsNone(self.sources.checkpoint("salesforce", "globex-salesforce-prod", "Account"))
        self.assertEqual(0, self.identity.count("source_record"))

    def test_09_late_update_is_historical_but_not_current(self) -> None:
        """An out-of-order update is retained without replacing a newer source state."""
        newest = self.process(example("globex-salesforce-account-updated.json"))
        late = example("globex-salesforce-account-created.json")
        late["event_id"] = "evt-sf-account-001-late"
        late["timestamps"]["source_updated_at"] = "2026-10-11T13:55:00Z"
        late["timestamps"]["observed_at"] = "2026-10-11T14:06:00Z"
        late["payload"]["LastModifiedDate"] = "2026-10-11T13:55:00Z"
        late["payload"]["Website"] = "https://old.globex.example"
        late["checkpoint"]["cursor"] = "sf-account-cursor-0002-late"
        late["checkpoint"]["high_watermark_at"] = "2026-10-11T14:06:10Z"
        result = self.process(late)
        self.assertFalse(result.became_current)
        self.assertEqual(2, len(self.sources.history_for_source(newest.source_record_id)))
        current = self.sources.current_state(newest.source_record_id)
        self.assertEqual("evt-sf-account-001-v2", current["latest_event_id"])
        checkpoint = self.sources.checkpoint("salesforce", "globex-salesforce-prod", "Account")
        self.assertEqual("sf-account-cursor-0002-late", checkpoint["cursor"])

    def test_10_simulated_failure_rolls_back_history_and_checkpoint_then_retries(self) -> None:
        """A post-identity failure keeps raw input, avoids partial source state, and retries safely."""
        created = self.process(example("globex-salesforce-account-created.json"))
        update = example("globex-salesforce-account-updated.json")
        with self.assertRaises(SimulatedFailure):
            self.process(update, simulate_failure=True)
        failed = self.sources.get_event(update["event_id"])
        self.assertEqual("failed", failed["processing_status"])
        self.assertEqual(1, len(self.sources.history_for_source(created.source_record_id)))
        self.assertEqual("sf-account-cursor-0001", self.sources.checkpoint(
            "salesforce", "globex-salesforce-prod", "Account"
        )["cursor"])
        self.assertEqual(2, self.identity.count("source_observation"))

        recovered = self.process(update)
        self.assertFalse(recovered.replayed)
        self.assertEqual(2, len(self.sources.history_for_source(created.source_record_id)))
        self.assertEqual("sf-account-cursor-0002", self.sources.checkpoint(
            "salesforce", "globex-salesforce-prod", "Account"
        )["cursor"])
        self.assertEqual(2, self.identity.count("source_observation"))

    def test_11_overlap_window_replays_before_high_watermark(self) -> None:
        """The next extraction starts five minutes early so late vendor updates can reappear."""
        self.process(example("globex-salesforce-account-created.json"))
        window = self.sources.replay_window("salesforce", "globex-salesforce-prod", "Account")
        self.assertEqual(300, window["overlap_seconds"])
        self.assertEqual("2026-10-11T13:55:10.000000Z", window["replay_from"])

    def test_12_event_id_cannot_be_reused_for_different_content(self) -> None:
        """A stable event ID cannot silently acquire a different payload during replay."""
        original = example("globex-salesforce-account-created.json")
        self.process(original)
        changed = copy.deepcopy(original)
        changed["payload"]["Name"] = "Different Company"
        with self.assertRaises(ConflictError):
            self.process(changed)
        self.assertEqual(1, self.sources.count("source_event"))

    def test_13_source_processing_never_auto_approves_identity(self) -> None:
        """A valid source record remains unresolved until P1.2 receives explicit evidence and approval."""
        result = self.process(example("globex-hubspot-company.json"))
        case = self.identity.resolution_case_for_source(result.source_record_id)
        self.assertEqual("unresolved", case["status"])
        self.assertIsNone(self.identity.active_mapping_for_source(result.source_record_id))


if __name__ == "__main__":
    unittest.main()
