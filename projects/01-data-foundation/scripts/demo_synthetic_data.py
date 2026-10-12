#!/usr/bin/env python3
"""Run the P1.5 Globex Health synthetic-data demonstration."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_authority import AuthorityStore, FieldChange  # noqa: E402
from sai_revenueos_identity import IDENTITY_WRITER, IdentityStore  # noqa: E402
from sai_revenueos_sources import SourceEvent, SourceStore, standardize_event  # noqa: E402
from sai_revenueos_synthetic import (  # noqa: E402
    GenerationConfig,
    generate_dataset,
    validate_dataset,
    write_dataset,
)


def show(label: str, value: Any) -> None:
    print("\n%s" % label)
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main() -> int:
    """Generate Globex fixtures and exercise existing identity and authority interfaces."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=25, help="Company count, minimum 3 (default: 25).")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed (default: 42).")
    parser.add_argument("--verbose", action="store_true", help="Show complete records and outcomes.")
    args = parser.parse_args()
    try:
        config = GenerationConfig(company_count=args.companies, seed=args.seed)
    except ValueError as exc:
        parser.error(str(exc))

    dataset = generate_dataset(config)
    report = validate_dataset(dataset)
    report.raise_for_errors()
    globex = dataset.companies[0]
    diagnostics = dataset.companies[1]
    northstar = dataset.companies[2]
    sf_document = next(
        item for item in dataset.salesforce_events
        if item["event_id"] == "p15-sf-account-000000-v1"
    )
    hs_document = next(
        item for item in dataset.hubspot_events
        if item["event_id"] == "p15-hs-company-000000-v1"
    )
    sf_event = SourceEvent.from_dict(sf_document)
    hs_event = SourceEvent.from_dict(hs_document)

    with tempfile.TemporaryDirectory(prefix="sai-revenueos-p15-") as temp:
        root = Path(temp)
        paths = write_dataset(dataset, root / "generated")
        with ExitStack() as stack:
            identity = stack.enter_context(IdentityStore(str(root / "identity.db")))
            sources = stack.enter_context(SourceStore(str(root / "sources.db")))
            authority = stack.enter_context(AuthorityStore(str(root / "authority.db")))
            canonical_id = identity.create_canonical_identity(
                "Account", "p1.5-demo", IDENTITY_WRITER, "p15-demo-globex"
            )
            sf_result = sources.process_event(sf_event, identity)
            hs_result = sources.process_event(hs_event, identity)
            sf_case = identity.resolution_case_for_source(sf_result.source_record_id)
            hs_case = identity.resolution_case_for_source(hs_result.source_record_id)

            sf_change = FieldChange.from_source_event(
                sf_event, sf_result.source_record_id, "Account", canonical_id,
                "lifecycle_status", sf_event.payload["Lifecycle_Status__c"],
                "p15-demo-sf-lifecycle",
            )
            hs_change = FieldChange.from_source_event(
                hs_event, hs_result.source_record_id, "Account", canonical_id,
                "lifecycle_status", hs_event.payload["properties"]["lifecyclestage"],
                "p15-demo-hs-lifecycle",
            )
            sf_authority = authority.apply_change(sf_change, identity)
            hs_authority = authority.apply_change(hs_change, identity)
            conflict = authority.get_conflict(hs_authority.conflict_id)
            current = authority.current_value("Account", canonical_id, "lifecycle_status")

            issue_counts = Counter(item["issue_type"] for item in dataset.quality_issues)
            print("P1.5 Globex synthetic-data demo (fictional; no vendor API called)")
            print("Config: companies=%d; seed=%d; fingerprint=%s" % (
                config.company_count, config.seed, dataset.fingerprint()[:12]
            ))
            print("Generated: companies=%d; people=%d; opportunities=%d; activities=%d" % (
                len(dataset.companies), len(dataset.people),
                len(dataset.opportunities), len(dataset.activities),
            ))
            print("Source events: Salesforce=%d; HubSpot=%d; all %d contract-valid" % (
                len(dataset.salesforce_events), len(dataset.hubspot_events), report.checked_source_events
            ))
            print("Relationships: Globex parent -> %s; acquisition -> %s" % (
                diagnostics["name"], northstar["name"]
            ))
            print("History: Northstar rebrand preserved; late/out-of-order streams=%d" % report.late_event_streams)
            print("Quality issues: duplicates=%d; missing=%d; conflicts=%d" % (
                issue_counts["duplicate_record"] + issue_counts["duplicate_event"],
                issue_counts["missing_optional_field"], issue_counts["conflicting_information"],
            ))
            print("Globex sources: Salesforce=%s; HubSpot=%s" % (
                globex["salesforce_account_id"], globex["hubspot_company_id"]
            ))
            print("Identity decision: Salesforce=%s; HubSpot=%s; automatic mappings=0" % (
                sf_case["status"], hs_case["status"]
            ))
            print("Field conflict: Salesforce=%s; HubSpot=%s" % (
                sf_change.proposed_value, hs_change.proposed_value
            ))
            print("Authority outcome: current=%s; HubSpot=%s; review owner=%s" % (
                current["value"], hs_authority.status, conflict["assigned_owner_role"]
            ))
            print("Expected identity: Globex needs review; acquired Northstar stays separate")
            print("Outcome: fixtures validated; no identity auto-merge or external write occurred")

            if args.verbose:
                show("GENERATED FILES", {name: str(path) for name, path in paths.items()})
                show("GLOBEX CANONICAL FIXTURE", globex)
                show("SALESFORCE INPUT", sf_document)
                show("HUBSPOT INPUT", hs_document)
                show("STANDARDIZED SOURCE VALUES", {
                    "salesforce": standardize_event(sf_event),
                    "hubspot": standardize_event(hs_event),
                })
                show("P1.2 IDENTITY CASES", {
                    "salesforce": sf_case,
                    "hubspot": hs_case,
                    "salesforce_active_mapping": identity.active_mapping_for_source(sf_result.source_record_id),
                    "hubspot_active_mapping": identity.active_mapping_for_source(hs_result.source_record_id),
                })
                show("P1.4 AUTHORITY EVALUATION", {
                    "salesforce": asdict(sf_authority),
                    "hubspot": asdict(hs_authority),
                    "current": current,
                    "conflict": conflict,
                })
                show("EXPECTED IDENTITY OUTCOMES", dataset.expected_identity_outcomes)
                show("SCENARIO MANIFEST", dataset.manifest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
