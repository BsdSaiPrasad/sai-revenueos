#!/usr/bin/env python3
"""Show one real HubSpot Globex record from Snowflake RAW through dbt staging."""

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


def _safe_identifier(value: str) -> str:
    if not value.replace("_", "").isalnum() or not value[0].isalpha():
        raise ValueError("unsafe Snowflake identifier: %s" % value)
    return value.upper()


def _query(connection: Any, sql: str) -> List[Dict[str, Any]]:
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        names = [str(column[0]).lower() for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()


def summary_lines(raw_rows: List[Dict[str, Any]], staged: Dict[str, Any]) -> List[str]:
    """Return the required concise learning summary in at most 15 lines."""
    first = raw_rows[0]
    latest = raw_rows[-1]
    return [
        "P1.7 Globex Snowflake + dbt demo (authenticated test data)",
        "Path: HubSpot API -> SQLite history -> Snowflake RAW -> dbt staging",
        "RAW history rows: %d" % len(raw_rows),
        "Before name: %s" % first["company_name"],
        "After name: %s" % latest["company_name"],
        "RAW latest event: %s" % latest["event_id"],
        "dbt model: SAI_REVENUEOS.STAGING.STG_HUBSPOT_COMPANIES",
        "Standardized ID: %s" % staged["source_object_id"],
        "Standardized name: %s" % staged["name"],
        "Typed source time: %s" % staged["source_updated_at"],
        "Provenance: hubspot tenant=%s" % staged["source_tenant"],
        "Identity outcome: source record preserved; no canonical auto-merge",
        "Outcome: RAW evidence and normalized history agree",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="Print the SQL and complete query rows.")
    args = parser.parse_args()
    database = _safe_identifier(os.environ.get("SNOWFLAKE_DATABASE", "SAI_REVENUEOS"))
    raw_schema = _safe_identifier(os.environ.get("SNOWFLAKE_RAW_SCHEMA", "RAW"))
    staging_schema = _safe_identifier(os.environ.get("SNOWFLAKE_STAGING_SCHEMA", "STAGING"))
    raw_sql = """
SELECT EVENT_ID,
       SOURCE_UPDATED_AT,
       RAW_PAYLOAD_JSON:properties:name::STRING AS COMPANY_NAME,
       RAW_PAYLOAD_JSON:properties:domain::STRING AS DOMAIN
FROM {database}.{raw_schema}.SOURCE_EVENT
WHERE SOURCE_SYSTEM = 'hubspot'
  AND SOURCE_OBJECT_TYPE = 'Company'
  AND RAW_PAYLOAD_JSON:properties:domain::STRING = 'globex-p16.invalid'
ORDER BY TRY_TO_TIMESTAMP_TZ(SOURCE_UPDATED_AT), RECEIVED_AT, EVENT_ID
""".format(database=database, raw_schema=raw_schema)
    staging_sql = """
SELECT SOURCE_OBJECT_ID, NAME, SOURCE_UPDATED_AT, SOURCE_TENANT, EVENT_ID
FROM {database}.{staging_schema}.STG_HUBSPOT_COMPANIES
WHERE DOMAIN = 'globex-p16.invalid'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY SOURCE_SYSTEM, SOURCE_TENANT, SOURCE_OBJECT_ID
    ORDER BY SOURCE_UPDATED_AT DESC, OBSERVED_AT DESC, EVENT_ID DESC
) = 1
""".format(database=database, staging_schema=staging_schema)

    connection = connect_to_snowflake("SNOWFLAKE_DBT_ROLE")
    try:
        raw_rows = _query(connection, raw_sql)
        staged_rows = _query(connection, staging_sql)
    finally:
        connection.close()
    if len(raw_rows) < 2:
        raise RuntimeError("expected at least two stored HubSpot Globex versions")
    if len(staged_rows) != 1:
        raise RuntimeError("expected exactly one latest staged HubSpot Globex row")
    if raw_rows[-1]["company_name"] != staged_rows[0]["name"]:
        raise RuntimeError("latest RAW and staged Globex names disagree")

    print("\n".join(summary_lines(raw_rows, staged_rows[0])))
    if args.verbose:
        print("\nRAW SQL\n%s" % raw_sql.strip())
        print("\nRAW RESULTS\n%s" % json.dumps(raw_rows, indent=2, default=str))
        print("\nSTAGING SQL\n%s" % staging_sql.strip())
        print("\nSTAGING RESULT\n%s" % json.dumps(staged_rows[0], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
