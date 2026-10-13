#!/usr/bin/env python3
"""Demonstrate P1.8 matching, human approval, crosswalk, and survivorship."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


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
from sai_revenueos_resolution import ResolutionService, ResolutionStore, StagedIdentityRecord  # noqa: E402


AT = "2026-10-13T14:00:00.000000Z"


def _source(identity: IdentityStore, system: str, object_type: str, object_id: str, event_id: str) -> str:
    return identity.get_or_create_source_record(
        system, "sai-demo", object_type, object_id, event_id,
        "p1.8-demo", SOURCE_WRITER, event_id, "snowflake://%s" % event_id, AT,
    )


def run_demo() -> Dict[str, Any]:
    """Execute the same public P1.2/P1.4/P1.8 interfaces used by tests."""
    with IdentityStore() as identity, ResolutionStore() as resolution, AuthorityStore() as authority:
        account_id = identity.create_canonical_identity(
            "Account", "sarah-kim", IDENTITY_WRITER, "p18-demo-account", AT
        )
        sf_source = _source(identity, "salesforce", "Account", "001GLOBEX", "p18-sf-globex")
        hs_source = _source(identity, "hubspot", "Company", "501", "p18-hs-globex")
        salesforce = StagedIdentityRecord(
            event_id="p18-sf-globex", source_record_id=sf_source,
            source_system="salesforce", source_tenant="sai-demo",
            source_object_type="Account", source_object_id="001GLOBEX",
            entity_type="Account", name="Globex Health", domain="globex.example",
            country="United States", source_updated_at=AT, observed_at=AT,
            trace_id="trace-p18-sf", payload_sha256="a" * 64,
            raw_payload={"Lifecycle_Status__c": "customer"},
            staging_model="STG_CRM_COMPANIES",
        )
        hubspot = StagedIdentityRecord(
            event_id="p18-hs-globex", source_record_id=hs_source,
            source_system="hubspot", source_tenant="sai-demo",
            source_object_type="Company", source_object_id="501",
            entity_type="Account", name="Globex Health, Inc.",
            domain="https://www.globex.example", country="United States",
            source_updated_at=AT, observed_at=AT, trace_id="trace-p18-hs",
            payload_sha256="b" * 64,
            raw_payload={"properties": {"lifecyclestage": "marketingqualifiedlead"}},
            staging_model="STG_CRM_COMPANIES",
        )
        records = [salesforce, hubspot]

        seed_candidate = identity.propose_candidate(
            sf_source, account_id, "known_fixture", "p18://demo/salesforce",
            1.0, "manual", "demo-v1", "sarah-kim", RESOLUTION_WRITER,
            "p18-demo-seed-proposal", AT,
        )
        identity.decide_candidate(
            seed_candidate, "accepted", "verified Salesforce Globex fixture",
            "sarah-kim", IDENTITY_STEWARD, "p18-demo-seed-decision", AT,
        )
        identity.activate_mapping(
            seed_candidate, "sarah-kim", IDENTITY_STEWARD,
            "p18-demo-seed-crosswalk", AT,
        )

        service = ResolutionService(identity, resolution)
        before = identity.resolution_case_for_source(hs_source)
        match = service.resolve(hubspot, records)
        repeated = service.resolve(hubspot, records)
        review = resolution.get_review(match.review_id)
        candidate_id = review["candidate_evidence_ids"][0]
        pre_approval_mapping = identity.active_mapping_for_source(hs_source)
        approval = service.approve(
            match.review_id, candidate_id, "sarah-kim", IDENTITY_STEWARD,
            "domain and company-name evidence verified",
        )
        after = identity.resolution_case_for_source(hs_source)
        mapping = identity.active_mapping_for_source(hs_source)
        survivor_results = service.apply_survivorship(account_id, records, authority)
        current = authority.current_value("Account", account_id, "lifecycle_status")
        conflicts = authority.count("field_conflict")
        output = service.approved_mapping_output("2026-10-13T14:30:00Z")
        return {
            "input": [record.fingerprint_payload() for record in records],
            "before": before,
            "match": {
                "run_id": match.run_id,
                "outcome": match.outcome,
                "candidate": {
                    "canonical_entity_id": match.candidates[0].canonical_entity_id,
                    "score": match.candidates[0].score,
                    "features": dict(match.candidates[0].features),
                },
                "review": review,
                "pre_approval_mapping": pre_approval_mapping,
            },
            "repeated": repeated.replayed,
            "approval": approval.__dict__,
            "after": after,
            "mapping": mapping,
            "survivorship_results": [result.__dict__ for result in survivor_results],
            "current": current,
            "conflicts": conflicts,
            "output": output,
            "resolution_audit": resolution.audit_history(),
            "authority_audit": authority.audit_history(),
        }


def summary_lines(result: Dict[str, Any]) -> List[str]:
    """Return a complete beginner summary in at most 15 lines."""
    candidate = result["match"]["candidate"]
    return [
        "P1.8 Globex identity-resolution demo (synthetic staged data)",
        "Input: Salesforce Account + HubSpot Company from P1.7-shaped rows",
        "Before: HubSpot case=%s; active crosswalk=none" % result["before"]["status"],
        "Match: exact domain=%s; name similarity=%s" % (
            candidate["features"]["exact_domain"], candidate["features"]["name_similarity"]
        ),
        "Candidate: canonical Globex Account; score=%.2f" % candidate["score"],
        "Review: pending; human approval required",
        "Automatic merge/activation: blocked",
        "Duplicate processing: replayed=%s; no duplicate review" % result["repeated"],
        "Decision: Sarah Kim approved the candidate",
        "After: HubSpot case=%s; crosswalk=active" % result["after"]["status"],
        "Crosswalk target: %s" % result["mapping"]["canonical_entity_id"],
        "Survivor: lifecycle_status=%s from %s" % (
            result["current"]["value"], result["current"]["source_system"]
        ),
        "Conflict: HubSpot lifecycle preserved for review=%s" % bool(result["conflicts"]),
        "P1.9 boundary: %d approved mappings; no proposed candidates" % len(result["output"]["mappings"]),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print complete evidence and audit output.")
    args = parser.parse_args()
    result = run_demo()
    print("\n".join(summary_lines(result)))
    if args.verbose:
        print("\nTECHNICAL EVIDENCE\n%s" % json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
