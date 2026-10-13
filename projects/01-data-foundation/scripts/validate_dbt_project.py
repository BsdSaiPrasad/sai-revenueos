#!/usr/bin/env python3
"""Validate P1.7 staging and its P1.8 identity-input view without credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
DBT = PROJECT / "warehouse/dbt"
POLICY = PROJECT / "contracts/warehouse-normalization-policy.v1.json"


def main() -> int:
    errors = []
    required = [
        DBT / "dbt_project.yml",
        DBT / "profiles.yml",
        DBT / "models/sources.yml",
        DBT / "models/staging/staging.yml",
        DBT / "models/staging/shared/stg_source_events.sql",
        DBT / "models/staging/shared/stg_crm_companies.sql",
        DBT / "models/staging/shared/stg_crm_people.sql",
        DBT / "seeds/p17_invalid_globex.csv",
        PROJECT / "warehouse/snowflake/bootstrap.sql",
        PROJECT / "warehouse/snowflake/pat_auth_setup.sql",
        PROJECT / "scripts/configure_snowflake_auth.py",
        PROJECT / "scripts/run_snowflake_dbt.py",
        PROJECT / "scripts/load_source_events_to_snowflake.py",
        PROJECT / "scripts/demo_snowflake_dbt.py",
        PROJECT / "scripts/demo_dbt_failure.py",
    ]
    object_models = {
        "salesforce": ("accounts", "leads", "contacts", "opportunities"),
        "hubspot": ("companies", "contacts", "deals"),
    }
    for system, objects in object_models.items():
        for object_name in objects:
            required.append(DBT / "models/staging" / system / ("stg_%s_%s.sql" % (system, object_name)))
    for path in required:
        if not path.is_file():
            errors.append("missing %s" % path.relative_to(PROJECT))

    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append("warehouse policy cannot be loaded: %s" % exc)
        policy = {}
    if policy.get("contract_version") != "1.0.0":
        errors.append("warehouse policy must be version 1.0.0")
    if policy.get("platform", {}).get("warehouse") != "snowflake":
        errors.append("approved warehouse must remain Snowflake")
    if policy.get("platform", {}).get("local_substitute_allowed") is not False:
        errors.append("DuckDB or another local substitute must remain disallowed")

    combined = "\n".join(path.read_text(encoding="utf-8") for path in required if path.is_file())
    for marker in (
        "TRY_TO_TIMESTAMP_TZ",
        "TRY_TO_DECIMAL",
        "is_late_arriving",
        "raw_payload_json",
        "source_tenant",
        "source_object_id",
        "payload_sha256",
        "envelope_sha256",
        "failure_demo",
    ):
        if marker.casefold() not in combined.casefold():
            errors.append("P1.7 artifacts are missing %s" % marker)
    if "duckdb" in combined.casefold():
        errors.append("dbt project unexpectedly references DuckDB")
    profile = (DBT / "profiles.yml").read_text(encoding="utf-8") if (DBT / "profiles.yml").is_file() else ""
    if "env_var('SNOWFLAKE_ACCOUNT')" not in profile or "env_var('SNOWFLAKE_DBT_TOKEN'" not in profile:
        errors.append("dbt profile must read account and PAT values from environment variables")
    if "password: \"{{ env_var('SNOWFLAKE_DBT_TOKEN'" not in profile:
        errors.append("dbt PAT must not be stored literally in profiles.yml")
    for unsafe in ("private_key:", "token:"):
        if unsafe in profile.casefold():
            errors.append("dbt profile contains an unsupported secret-bearing field: %s" % unsafe)

    if errors:
        print("P1.7 dbt project validation FAILED:")
        for error in errors:
            print("  - %s" % error)
        return 1
    print("P1.7/P1.8 dbt validation PASSED: Snowflake RAW, 10 staging models, identity inputs, tests, lineage, and failure demo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
