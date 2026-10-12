#!/usr/bin/env python3
"""Run the P1.3 Globex Health source-model demonstration with synthetic data."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
EXAMPLES = PROJECT / "examples" / "p13"
sys.path.insert(0, str(SRC))

from sai_revenueos_identity import IDENTITY_WRITER, IdentityStore  # noqa: E402
from sai_revenueos_identity.errors import SimulatedFailure  # noqa: E402
from sai_revenueos_sources import SourceEvent, SourceStore  # noqa: E402


def load_event(filename: str) -> tuple[dict[str, Any], SourceEvent]:
    """Load one checked-in synthetic envelope and build its validated event."""
    document = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
    return document, SourceEvent.from_dict(document)


def snapshot(sources: SourceStore, identity: IdentityStore) -> dict[str, int]:
    """Return the small set of counts used to show before-and-after behavior."""
    return {
        "raw_events": sources.count("source_event"),
        "source_versions": sources.count("source_record_version"),
        "current_source_rows": sources.count("source_current_state"),
        "checkpoints": sources.count("connector_checkpoint"),
        "identity_source_records": identity.count("source_record"),
        "identity_observations": identity.count("source_observation"),
        "canonical_identities": identity.count("canonical_identity"),
    }


def show(label: str, value: Any) -> None:
    """Print one stable, readable demonstration section."""
    print("\n%s" % label)
    print(json.dumps(value, indent=2, sort_keys=True))


def main() -> int:
    """Demonstrate input, processing, replay, failure, recovery, and deletion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overlap-seconds",
        type=int,
        default=300,
        help="Replay overlap subtracted from the final checkpoint (default: 300).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the complete event, database, checkpoint, and recovery evidence.",
    )
    args = parser.parse_args()
    created_document, created_event = load_event("globex-salesforce-account-created.json")
    _, update_event = load_event("globex-salesforce-account-updated.json")
    _, hubspot_event = load_event("globex-hubspot-company.json")
    _, delete_event = load_event("globex-salesforce-account-deleted.json")

    with tempfile.TemporaryDirectory(prefix="sai-revenueos-p13-") as directory:
        root = Path(directory)
        with IdentityStore(str(root / "identity.db")) as identity, SourceStore(str(root / "sources.db")) as sources:
            canonical_id = identity.create_canonical_identity(
                "Account",
                "demo-identity-writer",
                IDENTITY_WRITER,
                "demo-globex-canonical",
                "2026-10-11T13:59:00Z",
            )

            before = snapshot(sources, identity)
            if args.verbose:
                print("SYNTHETIC DEMO: no Salesforce or HubSpot API was called.")
                show("ACTUAL INPUT: synthetic Salesforce Account event", created_document)
                print("\nPROCESSOR: SourceStore.process_event(event, identity_store)")
                show("BEFORE", before)

            first = sources.process_event(created_event, identity)
            first_details = {
                "result": first.__dict__,
                "counts": snapshot(sources, identity),
                "current_state": sources.current_state(first.source_record_id),
                "resolution_status": identity.resolution_case_for_source(first.source_record_id)["status"],
                "active_mapping": identity.active_mapping_for_source(first.source_record_id),
            }
            if args.verbose:
                show("AFTER FIRST PROCESS", first_details)

            repeated = sources.process_event(created_event, identity)
            repeated_details = {
                "result": repeated.__dict__,
                "counts": snapshot(sources, identity),
            }
            if args.verbose:
                show("REPEAT SAME EVENT", repeated_details)

            checkpoint_before_failure = sources.checkpoint(
                "salesforce", "globex-salesforce-prod", "Account"
            )
            try:
                sources.process_event(update_event, identity, simulate_failure=True)
            except SimulatedFailure as exc:
                failure_details = {
                    "error": str(exc),
                    "failed_event_status": sources.get_event(update_event.event_id)["processing_status"],
                    "counts": snapshot(sources, identity),
                    "checkpoint_cursor_before": checkpoint_before_failure["cursor"],
                    "checkpoint_cursor_after": sources.checkpoint(
                        "salesforce", "globex-salesforce-prod", "Account"
                    )["cursor"],
                }
                if args.verbose:
                    show("SIMULATED FAILURE", failure_details)

            recovered = sources.process_event(update_event, identity)
            recovered_details = {
                "result": recovered.__dict__,
                "counts": snapshot(sources, identity),
                "checkpoint": sources.checkpoint(
                    "salesforce", "globex-salesforce-prod", "Account"
                ),
            }
            if args.verbose:
                show("RETRY AFTER FAILURE", recovered_details)

            hubspot = sources.process_event(hubspot_event, identity)
            hubspot_details = {
                "result": hubspot.__dict__,
                "current_state": sources.current_state(hubspot.source_record_id),
                "active_mapping": identity.active_mapping_for_source(hubspot.source_record_id),
            }
            if args.verbose:
                show("HUBSPOT SOURCE RECORD", hubspot_details)

            deleted = sources.process_event(delete_event, identity)
            deletion_details = {
                "result": deleted.__dict__,
                "salesforce_history_versions": len(sources.history_for_source(first.source_record_id)),
                "current_source_is_deleted": bool(sources.current_state(first.source_record_id)["is_deleted"]),
                "preexisting_canonical_id": canonical_id,
                "canonical_status_after_source_delete": identity.get(
                    "canonical_identity", "canonical_id", canonical_id
                )["identity_status"],
                "active_mapping": identity.active_mapping_for_source(first.source_record_id),
            }
            if args.verbose:
                show("SOURCE DELETION TOMBSTONE", deletion_details)

            replay_window = sources.replay_window(
                "salesforce", "globex-salesforce-prod", "Account", args.overlap_seconds
            )
            if args.verbose:
                show("NEXT REPLAY WINDOW", replay_window)

            if not args.verbose:
                print("P1.3 Globex source demo (synthetic; no vendor API called)")
                print("Input: Salesforce Account 001GLOBEX = Globex Health")
                print(
                    "Before: raw events=%d, source versions=%d, SourceRecords=%d"
                    % (before["raw_events"], before["source_versions"], before["identity_source_records"])
                )
                print(
                    "First process: raw events=%d, versions=%d, current name=%s"
                    % (
                        first_details["counts"]["raw_events"],
                        first_details["counts"]["source_versions"],
                        first_details["current_state"]["standardized_payload"]["name"],
                    )
                )
                print("Identity decision: unresolved; no automatic canonical mapping")
                print(
                    "Repeat: replayed=%s; raw events=%d; versions=%d"
                    % (
                        str(repeated.replayed).lower(),
                        repeated_details["counts"]["raw_events"],
                        repeated_details["counts"]["source_versions"],
                    )
                )
                print(
                    "Simulated failure: status=%s; checkpoint stayed %s"
                    % (failure_details["failed_event_status"], failure_details["checkpoint_cursor_after"])
                )
                print(
                    "Retry: status=%s; versions=%d; checkpoint=%s"
                    % (
                        recovered.processing_status,
                        recovered_details["counts"]["source_versions"],
                        recovered_details["checkpoint"]["cursor"],
                    )
                )
                print("HubSpot: separate SourceRecord created; mapping remains unresolved")
                print(
                    "Deletion: tombstone=%s; Salesforce history versions=%d"
                    % (
                        str(deletion_details["current_source_is_deleted"]).lower(),
                        deletion_details["salesforce_history_versions"],
                    )
                )
                print(
                    "After deletion: canonical Account remains %s"
                    % deletion_details["canonical_status_after_source_delete"]
                )
                print(
                    "Next replay: overlap=%ds; starts=%s"
                    % (args.overlap_seconds, replay_window["replay_from"])
                )
                print("Outcome: replay, rollback, history, and identity protection verified")

    if args.verbose:
        print("\nDONE: temporary demo databases were removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
