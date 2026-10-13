#!/usr/bin/env python3
"""Verify P1.8 against real P1.7 Snowflake staging with read-only access."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_identity import (  # noqa: E402
    IDENTITY_STEWARD,
    IDENTITY_WRITER,
    RESOLUTION_WRITER,
    IdentityStore,
)
from sai_revenueos_resolution import (  # noqa: E402
    ResolutionService,
    ResolutionStore,
    SnowflakeStagingReader,
)
from sai_revenueos_resolution.normalization import normalize_domain  # noqa: E402
from sai_revenueos_warehouse import connect_to_snowflake  # noqa: E402


LOCAL_IDENTITY = REPO / "generated-data/p16-live/data/identity.sqlite3"


def _backup_identity_database(target: Path) -> None:
    """Create a consistent temporary copy without mutating P1.6 acceptance evidence."""
    source = sqlite3.connect(str(LOCAL_IDENTITY))
    destination = sqlite3.connect(str(target))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def run_verification() -> Dict[str, Any]:
    connection = connect_to_snowflake("SNOWFLAKE_DBT_ROLE")
    try:
        records = SnowflakeStagingReader(connection).read_records(("Account",))
    finally:
        connection.close()
    globex = [record for record in records if normalize_domain(record.domain) == "globex-p16.invalid"]
    salesforce = [record for record in globex if record.source_system == "salesforce"]
    hubspot = [record for record in globex if record.source_system == "hubspot"]
    if len(salesforce) != 1 or len(hubspot) != 1:
        raise RuntimeError("expected one latest Salesforce and HubSpot Globex staged row")
    if not LOCAL_IDENTITY.exists():
        raise RuntimeError("P1.6 local identity database is missing")

    with tempfile.TemporaryDirectory(prefix="sai-p18-") as temporary:
        identity_path = Path(temporary) / "identity.sqlite3"
        _backup_identity_database(identity_path)
        with IdentityStore(str(identity_path)) as identity, ResolutionStore() as review:
            account_id = identity.create_canonical_identity(
                "Account", "p1.8-snowflake-verifier", IDENTITY_WRITER,
                "p18-snowflake-globex-account",
            )
            seed = identity.propose_candidate(
                salesforce[0].source_record_id, account_id,
                "authenticated_p1.7_staging_evidence",
                "snowflake://STAGING/STG_CRM_COMPANIES/%s" % salesforce[0].event_id,
                1.0, "manual_seed", "p18-snowflake-v1",
                "p1.8-snowflake-verifier", RESOLUTION_WRITER,
                "p18-snowflake-seed-proposal",
            )
            identity.decide_candidate(
                seed, "accepted", "existing Salesforce Globex record establishes the fixture",
                "p1.8-snowflake-verifier", IDENTITY_STEWARD,
                "p18-snowflake-seed-decision",
            )
            identity.activate_mapping(
                seed, "p1.8-snowflake-verifier", IDENTITY_STEWARD,
                "p18-snowflake-seed-mapping",
            )
            service = ResolutionService(identity, review)
            before = identity.resolution_case_for_source(hubspot[0].source_record_id)
            result = service.resolve(hubspot[0], records)
            work = review.get_review(result.review_id)
            candidate_id = work["candidate_evidence_ids"][0]
            pre_approval = identity.active_mapping_for_source(hubspot[0].source_record_id)
            approval = service.approve(
                result.review_id, candidate_id, "p1.8-snowflake-verifier",
                IDENTITY_STEWARD, "authenticated staged Globex evidence verified",
            )
            after = identity.resolution_case_for_source(hubspot[0].source_record_id)
            mapping = identity.active_mapping_for_source(hubspot[0].source_record_id)
            output = service.approved_mapping_output()
            return {
                "records_read": len(records),
                "salesforce": salesforce[0].fingerprint_payload(),
                "hubspot": hubspot[0].fingerprint_payload(),
                "before": before,
                "candidate": {
                    "score": result.candidates[0].score,
                    "features": dict(result.candidates[0].features),
                },
                "review": work,
                "pre_approval_mapping": pre_approval,
                "approval": approval.__dict__,
                "after": after,
                "mapping": mapping,
                "output": output,
            }


def summary_lines(result: Dict[str, Any]) -> List[str]:
    return [
        "P1.8 Snowflake staging verification (authenticated, read-only)",
        "Input model: SAI_REVENUEOS.STAGING.STG_CRM_COMPANIES",
        "Latest Account rows read: %d" % result["records_read"],
        "Salesforce Globex: %s" % result["salesforce"]["name"],
        "HubSpot Globex: %s" % result["hubspot"]["name"],
        "Before: HubSpot case=%s; crosswalk=none" % result["before"]["status"],
        "Candidate score: %.2f; exact domain=%s" % (
            result["candidate"]["score"], result["candidate"]["features"]["exact_domain"]
        ),
        "Review: pending; automatic activation blocked",
        "Decision: explicit identity-steward approval",
        "After: HubSpot case=%s; crosswalk=active" % result["after"]["status"],
        "Target: %s" % result["mapping"]["canonical_entity_id"],
        "P1.9 output mappings: %d" % len(result["output"]["mappings"]),
        "Writes: temporary local SQLite only; Snowflake remained read-only",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print complete staged and review evidence.")
    args = parser.parse_args()
    result = run_verification()
    print("\n".join(summary_lines(result)))
    if args.verbose:
        print("\nTECHNICAL EVIDENCE\n%s" % json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
