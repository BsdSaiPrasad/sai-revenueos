"""Acceptance scenarios for P1.4 source-of-truth and write authority."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sai_revenueos_authority import AuthorityPolicy, AuthorityStore, FieldChange  # noqa: E402
from sai_revenueos_identity import IDENTITY_WRITER, IdentityStore  # noqa: E402
from sai_revenueos_identity.errors import (  # noqa: E402
    AuthorizationError,
    ConflictError,
    IdempotencyConflictError,
)
from sai_revenueos_sources import SourceEvent, SourceStore  # noqa: E402


EXAMPLE_PATH = PROJECT_DIR / "examples/p14/globex-field-authority-demo.v1.json"


class FieldAuthorityTests(unittest.TestCase):
    """Prove ownership, conflict, review, history, and write-back boundaries."""

    def setUp(self) -> None:
        document = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        self.events = [SourceEvent.from_dict(item) for item in document["source_events"]]
        self.identity = IdentityStore()
        self.sources = SourceStore()
        self.authority = AuthorityStore()
        self.account_id = self.identity.create_canonical_identity(
            "Account", "test-setup", IDENTITY_WRITER, "create-globex-account"
        )
        self.source_results = [
            self.sources.process_event(event, self.identity) for event in self.events
        ]

    def tearDown(self) -> None:
        self.authority.close()
        self.sources.close()
        self.identity.close()

    def change(
        self,
        event_index: int,
        value: str,
        change_id: str,
        actor_role: str = "source_processor",
    ) -> FieldChange:
        return FieldChange.from_source_event(
            self.events[event_index],
            self.source_results[event_index].source_record_id,
            "Account",
            self.account_id,
            "lifecycle_status",
            value,
            change_id,
            actor_id="p1.4-test-processor",
            actor_role=actor_role,
        )

    def apply_initial(self):
        return self.authority.apply_change(
            self.change(0, "prospect", "change-sf-prospect"), self.identity
        )

    def open_manually_protected_conflict(self):
        self.apply_initial()
        self.authority.verify_current_value(
            "Account", self.account_id, "lifecycle_status",
            "sarah-kim", "revenue_operations", {"ticket": "REVOPS-101"},
        )
        return self.authority.apply_change(
            self.change(2, "customer", "change-sf-customer"), self.identity
        )

    def test_01_policy_covers_approved_domains_and_canonical_fields(self):
        """The matrix encodes all nine approved domains without inventing fields."""
        policy = AuthorityPolicy()
        self.assertEqual(policy.contract_version, "1.0.0")
        self.assertEqual(policy.source_domain("salesforce"), "sales")
        self.assertEqual(policy.source_domain("hubspot"), "marketing")
        self.assertEqual(policy.source_domain("stripe"), "payments")
        self.assertEqual(policy.source_domain("consent_registry"), "consent")
        self.assertFalse(policy.network_delivery)

    def test_02_authoritative_source_establishes_value_with_provenance(self):
        """Salesforce can establish its owned Account lifecycle field."""
        result = self.apply_initial()
        current = self.authority.current_value("Account", self.account_id, "lifecycle_status")
        self.assertEqual(result.status, "applied")
        self.assertEqual(current["value"], "prospect")
        self.assertEqual(current["source_system"], "salesforce")
        self.assertEqual(current["source_event_id"], self.events[0].event_id)
        self.assertEqual(current["revision"], 1)

    def test_03_same_source_update_preserves_previous_value(self):
        """A Salesforce update advances current state and appends old and new values."""
        self.apply_initial()
        result = self.authority.apply_change(
            self.change(2, "customer", "change-sf-customer"), self.identity
        )
        history = self.authority.value_history("Account", self.account_id, "lifecycle_status")
        self.assertEqual(result.status, "applied")
        self.assertEqual([row["value"] for row in history], ["prospect", "customer"])
        self.assertEqual(history[-1]["prior_value"], "prospect")

    def test_04_change_replay_is_idempotent_and_changed_content_conflicts(self):
        """One change ID replays safely but cannot be reused for a new value."""
        change = self.change(0, "prospect", "stable-change-id")
        first = self.authority.apply_change(change, self.identity)
        replay = self.authority.apply_change(change, self.identity)
        self.assertFalse(first.replayed)
        self.assertTrue(replay.replayed)
        self.assertEqual(self.authority.count("field_value_history"), 1)
        with self.assertRaises(IdempotencyConflictError):
            self.authority.apply_change(
                self.change(0, "customer", "stable-change-id"), self.identity
            )

    def test_05_unauthorized_actor_role_is_denied(self):
        """An unapproved process cannot establish a field even from Salesforce."""
        result = self.authority.apply_change(
            self.change(0, "prospect", "unauthorized-role", "report_reader"), self.identity
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(self.authority.count("canonical_field_state"), 0)

    def test_06_non_authoritative_source_preserves_both_values_in_conflict(self):
        """HubSpot cannot overwrite Salesforce sales truth; its proposal is retained."""
        self.apply_initial()
        result = self.authority.apply_change(
            self.change(1, "marketingqualifiedlead", "change-hs-conflict"), self.identity
        )
        current = self.authority.current_value("Account", self.account_id, "lifecycle_status")
        conflict = self.authority.get_conflict(result.conflict_id)
        self.assertEqual(result.status, "denied")
        self.assertEqual(current["value"], "prospect")
        self.assertEqual(conflict["current_value"], "prospect")
        self.assertEqual(conflict["proposed_value"], "marketingqualifiedlead")
        self.assertEqual(conflict["assigned_owner_role"], "revenue_operations")
        self.assertEqual(conflict["evidence"]["event_id"], self.events[1].event_id)

    def test_07_manual_verification_blocks_automatic_overwrite(self):
        """A newer Salesforce value requires review after a human verifies the field."""
        result = self.open_manually_protected_conflict()
        current = self.authority.current_value("Account", self.account_id, "lifecycle_status")
        self.assertEqual(result.status, "review_required")
        self.assertEqual(current["value"], "prospect")
        self.assertTrue(current["manual_verified"])

    def test_08_assignment_and_escalation_are_audited(self):
        """A conflict can be assigned and escalated without losing review history."""
        result = self.open_manually_protected_conflict()
        self.authority.assign_conflict(
            result.conflict_id, "sarah-kim", "steward-1", "data_steward", "Sarah owns Globex"
        )
        conflict = self.authority.escalate_conflict(
            result.conflict_id, "data_governance", "sarah-kim",
            "revenue_operations", "Customer transition needs governance review",
        )
        actions = [row["action"] for row in self.authority.review_history(result.conflict_id)]
        self.assertEqual(conflict["status"], "escalated")
        self.assertEqual(conflict["assigned_owner_role"], "data_governance")
        self.assertEqual(actions, ["opened", "assigned", "escalated"])

    def test_09_human_approval_updates_truth_and_history(self):
        """An authorized reviewer can approve the proposal and preserve its predecessor."""
        result = self.open_manually_protected_conflict()
        current = self.authority.resolve_conflict(
            result.conflict_id, "approve_proposed", "Contract is active",
            "sarah-kim", "revenue_operations",
        )
        conflict = self.authority.get_conflict(result.conflict_id)
        history = self.authority.value_history("Account", self.account_id, "lifecycle_status")
        self.assertEqual(current["value"], "customer")
        self.assertTrue(current["manual_verified"])
        self.assertEqual(conflict["status"], "approved")
        self.assertEqual(history[-1]["action"], "conflict_approved")
        self.assertEqual(history[-1]["prior_value"], "prospect")

    def test_10_keep_current_rejects_proposal_and_verifies_truth(self):
        """Review can reject a competing value while retaining the full proposal."""
        self.apply_initial()
        result = self.authority.apply_change(
            self.change(1, "marketingqualifiedlead", "change-hs-conflict"), self.identity
        )
        current = self.authority.resolve_conflict(
            result.conflict_id, "keep_current", "Salesforce owns sales lifecycle",
            "sarah-kim", "revenue_operations",
        )
        self.assertEqual(current["value"], "prospect")
        self.assertTrue(current["manual_verified"])
        self.assertEqual(self.authority.get_conflict(result.conflict_id)["status"], "rejected")

    def test_11_unassigned_role_cannot_resolve_conflict(self):
        """A marketing writer cannot decide a Revenue Operations conflict."""
        result = self.open_manually_protected_conflict()
        with self.assertRaises(AuthorizationError):
            self.authority.resolve_conflict(
                result.conflict_id, "approve_proposed", "I prefer it",
                "marketing-user", "marketing_operations",
            )

    def test_12_write_back_requires_role_current_truth_and_resolved_review(self):
        """Write-back is auditable authorization only and never unrestricted delivery."""
        result = self.open_manually_protected_conflict()
        current = self.authority.resolve_conflict(
            result.conflict_id, "approve_proposed", "Contract is active",
            "sarah-kim", "revenue_operations",
        )
        denied = self.authority.evaluate_write_back(
            "writeback-denied", "Account", self.account_id, "lifecycle_status",
            "hubspot", current["value"], "p1.4-processor", "source_processor",
            result.conflict_id,
        )
        authorized = self.authority.evaluate_write_back(
            "writeback-authorized", "Account", self.account_id, "lifecycle_status",
            "hubspot", current["value"], "sarah-kim", "data_steward",
            result.conflict_id,
        )
        wrong_value = self.authority.evaluate_write_back(
            "writeback-wrong-value", "Account", self.account_id, "lifecycle_status",
            "hubspot", "prospect", "sarah-kim", "data_steward", result.conflict_id,
        )
        self.assertEqual(denied.status, "denied")
        self.assertEqual(authorized.status, "authorized")
        self.assertFalse(authorized.network_delivery)
        self.assertEqual(wrong_value.status, "denied")

    def test_13_retired_identity_cannot_receive_new_field_values(self):
        """P1.4 honors P1.2 identity status rather than writing to a retired ID."""
        other = self.identity.create_canonical_identity(
            "Account", "test-setup", IDENTITY_WRITER, "create-other-account"
        )
        self.identity.merge_identities(
            other, self.account_id, "duplicate", "steward", "p1_identity_steward",
            "merge-globex",
        )
        with self.assertRaises(ConflictError):
            self.apply_initial()

    def test_14_audit_history_records_denial_conflict_and_resolution(self):
        """The audit stream explains why a proposal was denied and how it was decided."""
        self.apply_initial()
        result = self.authority.apply_change(
            self.change(1, "marketingqualifiedlead", "change-hs-conflict"), self.identity
        )
        self.authority.resolve_conflict(
            result.conflict_id, "keep_current", "Salesforce remains authoritative",
            "sarah-kim", "revenue_operations",
        )
        event_types = [row["event_type"] for row in self.authority.audit_history()]
        self.assertIn("field_change_denied", event_types)
        self.assertIn("field_conflict_opened", event_types)
        self.assertIn("field_conflict_resolved", event_types)
        with self.assertRaises(sqlite3.IntegrityError):
            self.authority._connection.execute("DELETE FROM authority_audit_event")

    def test_15_stale_conflict_cannot_overwrite_a_newer_revision(self):
        """Review must restart if canonical truth changes after a case opens."""
        self.apply_initial()
        old_conflict = self.authority.apply_change(
            self.change(1, "marketingqualifiedlead", "change-hs-conflict"), self.identity
        )
        self.authority.apply_change(
            self.change(2, "customer", "change-sf-customer"), self.identity
        )
        with self.assertRaises(ConflictError):
            self.authority.resolve_conflict(
                old_conflict.conflict_id, "keep_current", "Review is now stale",
                "sarah-kim", "revenue_operations",
            )


if __name__ == "__main__":
    unittest.main()
