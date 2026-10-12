#!/usr/bin/env python3
"""Run the synthetic Globex Health P1.4 field-authority demonstration."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sai_revenueos_authority import AuthorityStore, FieldChange  # noqa: E402
from sai_revenueos_identity import IDENTITY_WRITER, IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceEvent, SourceStore  # noqa: E402


INPUT_PATH = PROJECT_DIR / "examples/p14/globex-field-authority-demo.v1.json"


def show(label: str, value: Any) -> None:
    """Print one readable, stable demonstration section."""
    print("\n%s" % label)
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salesforce-decision",
        choices=("approve_proposed", "keep_current"),
        default="approve_proposed",
        help="Human decision for Salesforce's manually protected lifecycle update.",
    )
    args = parser.parse_args()
    input_document = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    events = [SourceEvent.from_dict(item) for item in input_document["source_events"]]

    print("SYNTHETIC DEMO: no Salesforce, HubSpot, or write-back API is called.")
    show("ACTUAL INPUT", input_document)
    print("\nPROCESSORS")
    print("P1.3: SourceStore.process_event(event, identity_store)")
    print("P1.4: AuthorityStore.apply_change(change, identity_store)")

    with tempfile.TemporaryDirectory(prefix="sai-revenueos-p14-") as temp:
        root = Path(temp)
        with ExitStack() as stack:
            identity = stack.enter_context(IdentityStore(str(root / "identity.db")))
            sources = stack.enter_context(SourceStore(str(root / "sources.db")))
            authority = stack.enter_context(AuthorityStore(str(root / "authority.db")))
            account_id = identity.create_canonical_identity(
                "Account", "demo-setup", IDENTITY_WRITER, "demo-create-globex-account"
            )
            source_results = [sources.process_event(event, identity) for event in events]
            values = ["prospect", "marketingqualifiedlead", "customer"]
            changes = [
                FieldChange.from_source_event(
                    event, result.source_record_id, "Account", account_id,
                    "lifecycle_status", value, "p14-demo-change-%d" % (index + 1),
                )
                for index, (event, result, value) in enumerate(zip(events, source_results, values))
            ]

            show("BEFORE", {
                "globex_account_id": account_id,
                "canonical_field_rows": authority.count("canonical_field_state"),
                "conflicts": authority.count("field_conflict"),
                "source_events_processed": sources.count("source_record_version"),
                "source_records_reused_from_p1_2": identity.count("source_record"),
            })

            initial = authority.apply_change(changes[0], identity)
            replay = authority.apply_change(changes[0], identity)
            authority.verify_current_value(
                "Account", account_id, "lifecycle_status", "sarah-kim",
                "revenue_operations", {"review_ticket": "REVOPS-101"},
            )
            show("AUTHORITATIVE SALESFORCE VALUE + SAFE REPLAY", {
                "first_result": asdict(initial),
                "repeat_result": asdict(replay),
                "current": authority.current_value("Account", account_id, "lifecycle_status"),
            })

            hubspot = authority.apply_change(changes[1], identity)
            hubspot_case = authority.get_conflict(hubspot.conflict_id)
            show("HUBSPOT CONFLICT: VALUE PRESERVED, OVERWRITE DENIED", {
                "evaluation": asdict(hubspot),
                "conflict": hubspot_case,
                "current_still": authority.current_value("Account", account_id, "lifecycle_status"),
            })
            authority.assign_conflict(
                hubspot.conflict_id, "sarah-kim", "governance-steward",
                "data_steward", "Sarah owns the Globex review",
            )
            authority.resolve_conflict(
                hubspot.conflict_id, "keep_current", "Salesforce owns sales lifecycle",
                "sarah-kim", "revenue_operations",
            )

            salesforce_update = authority.apply_change(changes[2], identity)
            authority.assign_conflict(
                salesforce_update.conflict_id, "sarah-kim", "governance-steward",
                "data_steward", "Sarah reviews the verified value change",
            )
            current = authority.resolve_conflict(
                salesforce_update.conflict_id, args.salesforce_decision,
                "Reviewed against the synthetic signed-contract evidence",
                "sarah-kim", "revenue_operations",
            )
            show("HUMAN REVIEW DECISIONS", {
                "hubspot_conflict": authority.get_conflict(hubspot.conflict_id),
                "salesforce_conflict": authority.get_conflict(salesforce_update.conflict_id),
                "salesforce_review_history": authority.review_history(salesforce_update.conflict_id),
                "current_after_review": current,
            })

            denied_write = authority.evaluate_write_back(
                "p14-demo-write-denied", "Account", account_id, "lifecycle_status",
                "hubspot", current["value"], "automatic-sync", "source_processor",
                salesforce_update.conflict_id,
            )
            authorized_write = authority.evaluate_write_back(
                "p14-demo-write-authorized", "Account", account_id, "lifecycle_status",
                "hubspot", current["value"], "sarah-kim", "data_steward",
                salesforce_update.conflict_id,
            )
            show("CONTROLLED WRITE-BACK EVALUATION", {
                "unauthorized_request": asdict(denied_write),
                "steward_authorization": asdict(authorized_write),
                "important": "Authorization was recorded; nothing was sent to HubSpot.",
            })

            show("AFTER", {
                "current": current,
                "value_history": authority.value_history(
                    "Account", account_id, "lifecycle_status"
                ),
                "audit_event_types": [row["event_type"] for row in authority.audit_history()],
                "counts": {
                    "canonical_field_rows": authority.count("canonical_field_state"),
                    "value_history_rows": authority.count("field_value_history"),
                    "conflicts": authority.count("field_conflict"),
                    "review_events": authority.count("conflict_review_event"),
                    "write_back_decisions": authority.count("write_back_request"),
                },
            })

    print("\nDONE: temporary demo databases were removed; no external write occurred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
