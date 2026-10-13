#!/usr/bin/env python3
"""Create an isolated, explicit P1.8 approval fixture for P1.9 acceptance."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


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


BASE_IDENTITY = REPO / "generated-data/p16-live/data/identity.sqlite3"
OUTPUT_DIR = REPO / "generated-data/p19-canonical"
IDENTITY_DB = OUTPUT_DIR / "identity.sqlite3"
REVIEW_DB = OUTPUT_DIR / "resolution.sqlite3"
OUTPUT_JSON = OUTPUT_DIR / "identity-resolution-output.json"
ACTOR = "p1.9-fictional-acceptance-steward"


def _copy_identity_database() -> None:
    """Create a consistent acceptance copy without changing P1.6 evidence."""
    source = sqlite3.connect(str(BASE_IDENTITY))
    target = sqlite3.connect(str(IDENTITY_DB))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _seed_mapping(identity: IdentityStore, source_record_id: str, account_id: str) -> None:
    if identity.active_mapping_for_source(source_record_id) is not None:
        return
    candidate_id = identity.propose_candidate(
        source_record_id,
        account_id,
        "explicit_fictional_acceptance_fixture",
        "p19://globex-acceptance/salesforce",
        1.0,
        "manual_acceptance",
        "p19-v1",
        ACTOR,
        RESOLUTION_WRITER,
        "p19-globex-salesforce-proposal",
    )
    candidate = identity.get("candidate_evidence", "candidate_evidence_id", candidate_id)
    if candidate["disposition"] == "proposed":
        identity.decide_candidate(
            candidate_id,
            "accepted",
            "explicitly approved fictional Globex acceptance record",
            ACTOR,
            IDENTITY_STEWARD,
            "p19-globex-salesforce-decision",
        )
    identity.activate_mapping(
        candidate_id,
        ACTOR,
        IDENTITY_STEWARD,
        "p19-globex-salesforce-mapping",
    )


def prepare() -> dict:
    if not BASE_IDENTITY.is_file():
        raise RuntimeError("P1.6 identity database is missing")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not IDENTITY_DB.exists():
        _copy_identity_database()

    connection = connect_to_snowflake("SNOWFLAKE_DBT_ROLE")
    try:
        records = SnowflakeStagingReader(connection).read_records(("Account",))
    finally:
        connection.close()
    globex = [record for record in records if normalize_domain(record.domain) == "globex-p16.invalid"]
    salesforce = [record for record in globex if record.source_system == "salesforce"]
    hubspot = [record for record in globex if record.source_system == "hubspot"]
    if len(salesforce) != 1 or len(hubspot) != 1:
        raise RuntimeError("expected one latest Salesforce and HubSpot Globex row")

    with IdentityStore(str(IDENTITY_DB)) as identity, ResolutionStore(str(REVIEW_DB)) as review:
        mappings = [
            identity.active_mapping_for_source(salesforce[0].source_record_id),
            identity.active_mapping_for_source(hubspot[0].source_record_id),
        ]
        targets = {row["canonical_entity_id"] for row in mappings if row is not None}
        if len(targets) > 1:
            raise RuntimeError("Globex source records already map to different canonical Accounts")
        account_id = next(iter(targets), None)
        if account_id is None:
            account_id = identity.create_canonical_identity(
                "Account",
                ACTOR,
                IDENTITY_WRITER,
                "p19-globex-canonical-account",
            )
        _seed_mapping(identity, salesforce[0].source_record_id, account_id)

        if identity.active_mapping_for_source(hubspot[0].source_record_id) is None:
            service = ResolutionService(identity, review)
            result = service.resolve(hubspot[0], records)
            work = review.get_review(result.review_id)
            selected = next(
                candidate_id
                for candidate_id in work["candidate_evidence_ids"]
                if identity.get(
                    "candidate_evidence", "candidate_evidence_id", candidate_id
                )["candidate_canonical_id"] == account_id
            )
            service.approve(
                result.review_id,
                selected,
                ACTOR,
                IDENTITY_STEWARD,
                "explicitly approved fictional Globex staged evidence",
            )

        service = ResolutionService(identity, review)
        output = service.approved_mapping_output()
        OUTPUT_JSON.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        OUTPUT_JSON.chmod(0o600)
        return {
            "account_id": account_id,
            "salesforce_source_id": salesforce[0].source_object_id,
            "hubspot_source_id": hubspot[0].source_object_id,
            "mapping_count": len(output["mappings"]),
            "output": str(OUTPUT_JSON),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Show fictional source IDs and output path.")
    args = parser.parse_args()
    result = prepare()
    print("P1.9 fictional Globex approval fixture prepared")
    print("Canonical Account: %s" % result["account_id"])
    print("Approved mappings: %d" % result["mapping_count"])
    print("Boundary: isolated local P1.8 store; original P1.6 evidence unchanged")
    if args.verbose:
        print("Salesforce source ID: %s" % result["salesforce_source_id"])
        print("HubSpot source ID: %s" % result["hubspot_source_id"])
        print("Output: %s" % result["output"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
