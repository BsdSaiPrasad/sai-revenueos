#!/usr/bin/env python3
"""Show the real Globex path from CRM staging to P1.9 canonical Account."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_warehouse import connect_to_snowflake  # noqa: E402


def _identifier(value: str) -> str:
    if not value or not value[0].isalpha() or not value.replace("_", "").isalnum():
        raise ValueError("unsafe Snowflake identifier")
    return value.upper()


def _rows(connection: Any, sql: str) -> List[Dict[str, Any]]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        names = [str(column[0]).casefold() for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def summary_lines(result: Dict[str, Any]) -> List[str]:
    """Return the beginner-friendly P1.9 result in at most 15 lines."""
    sources = result["sources"]
    salesforce = next(row for row in sources if row["source_system"] == "salesforce")
    hubspot = next(row for row in sources if row["source_system"] == "hubspot")
    account = result["account"]
    lifecycle = account.get("lifecycle_status") or "not promoted (no authoritative value present)"
    return [
        "P1.9 Globex canonical-model demo (authenticated fictional data)",
        "Path: Salesforce + HubSpot -> dbt staging -> P1.8 approval -> canonical Account",
        "Before Salesforce source ID: %s" % salesforce["source_object_id"],
        "Before HubSpot source ID: %s" % hubspot["source_object_id"],
        "Approved mappings: both source records -> one canonical Account",
        "After canonical ID: %s" % account["account_id"],
        "Lifecycle: %s" % lifecycle,
        "Why: Salesforce alone owns Account lifecycle under P1.4",
        "Names/domains: %d source rows preserved; no unapproved owner invented" % len(sources),
        "Conflict evidence rows: %d" % len(result["conflicts"]),
        "Historical mapped events preserved: %d" % result["history_count"],
        "Unresolved example: %s remains source-only" % result["unresolved"]["source_object_id"],
        "Replay: publication count=%d; canonical Account count=1" % result["publication_count"],
        "Outcome: stable approved identity; P1.10 not started",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print read-only SQL and complete rows.")
    args = parser.parse_args()
    database = _identifier(os.environ.get("SNOWFLAKE_DATABASE", "SAI_REVENUEOS"))
    schema = _identifier(os.environ.get("SNOWFLAKE_STAGING_SCHEMA", "STAGING"))
    globex_sql = """
SELECT HISTORY.SOURCE_SYSTEM, HISTORY.SOURCE_OBJECT_ID, HISTORY.SOURCE_RECORD_ID,
       HISTORY.OBSERVED_NAME, HISTORY.OBSERVED_DOMAIN, HISTORY.OBSERVED_LIFECYCLE_STATUS,
       HISTORY.ACCOUNT_ID
FROM {database}.{schema}.CANONICAL_ACCOUNT_SOURCE_HISTORY HISTORY
WHERE HISTORY.IS_LATEST_SOURCE_VERSION = TRUE
  AND HISTORY.EVENT_TYPE = 'upsert'
  AND NOT HISTORY.IS_DELETED
  AND LOWER(HISTORY.OBSERVED_DOMAIN) LIKE '%globex-p16.invalid%'
ORDER BY HISTORY.SOURCE_SYSTEM
""".format(database=database, schema=schema)
    account_sql = """
SELECT ACCOUNT.*
FROM {database}.{schema}.CANONICAL_ACCOUNTS ACCOUNT
WHERE ACCOUNT.ACCOUNT_ID = %s
""".format(database=database, schema=schema)
    conflict_sql = """
SELECT *
FROM {database}.{schema}.CANONICAL_FIELD_CONFLICT_EVIDENCE
WHERE CANONICAL_ENTITY_ID = %s
ORDER BY FIELD_NAME, COMPETING_SOURCE_RECORD_ID
""".format(database=database, schema=schema)
    history_sql = """
SELECT COUNT(*) AS HISTORY_COUNT
FROM {database}.{schema}.CANONICAL_ACCOUNT_SOURCE_HISTORY
WHERE ACCOUNT_ID = %s
""".format(database=database, schema=schema)
    unresolved_sql = """
SELECT SOURCE_SYSTEM, SOURCE_OBJECT_TYPE, SOURCE_OBJECT_ID, SOURCE_RECORD_ID
FROM {database}.{schema}.UNRESOLVED_IDENTITY_RECORDS
ORDER BY SOURCE_SYSTEM, SOURCE_OBJECT_TYPE, SOURCE_OBJECT_ID
LIMIT 1
""".format(database=database, schema=schema)
    publication_sql = """
SELECT COUNT(*) AS PUBLICATION_COUNT
FROM {database}.{schema}.P18_IDENTITY_MAPPING_PUBLICATION
""".format(database=database, schema=schema)

    connection = connect_to_snowflake("SNOWFLAKE_DBT_ROLE")
    try:
        sources = _rows(connection, globex_sql)
        if len(sources) != 2 or len({row["account_id"] for row in sources}) != 1:
            raise RuntimeError("expected two approved Globex sources mapped to one Account")
        account_id = sources[0]["account_id"]
        cursor = connection.cursor()
        try:
            cursor.execute(account_sql, (account_id,))
            names = [str(column[0]).casefold() for column in cursor.description]
            account_rows = [dict(zip(names, row)) for row in cursor.fetchall()]
            cursor.execute(conflict_sql, (account_id,))
            names = [str(column[0]).casefold() for column in cursor.description]
            conflicts = [dict(zip(names, row)) for row in cursor.fetchall()]
            cursor.execute(history_sql, (account_id,))
            history_count = int(cursor.fetchone()[0])
        finally:
            cursor.close()
        unresolved = _rows(connection, unresolved_sql)
        publications = _rows(connection, publication_sql)
    finally:
        connection.close()
    if len(account_rows) != 1:
        raise RuntimeError("expected one canonical Globex Account")
    if not unresolved:
        raise RuntimeError("expected at least one unresolved source record")
    result = {
        "sources": sources,
        "account": account_rows[0],
        "conflicts": conflicts,
        "history_count": history_count,
        "unresolved": unresolved[0],
        "publication_count": int(publications[0]["publication_count"]),
    }
    print("\n".join(summary_lines(result)))
    if args.verbose:
        quoted_account_id = "'" + str(account_id).replace("'", "''") + "'"
        print("\nREAD-ONLY SQL\n%s" % globex_sql.strip())
        print("\n%s" % account_sql.strip().replace("%s", quoted_account_id))
        print("\n%s" % conflict_sql.strip().replace("%s", quoted_account_id))
        print("\n%s" % unresolved_sql.strip())
        print("\nRESULTS\n%s" % json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
