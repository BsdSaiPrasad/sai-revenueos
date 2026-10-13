#!/usr/bin/env python3
"""Store two Snowflake PATs locally without echoing or logging their values."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sai_revenueos_warehouse import credential_path  # noqa: E402


def _required_secret(label: str) -> str:
    value = getpass.getpass("%s (input hidden): " % label).strip()
    if not value:
        raise SystemExit("A token was not entered; no credential file was written")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True, help="Snowflake organization-account identifier")
    parser.add_argument("--loader-user", default="SAI_REVENUEOS_LOADER_SVC")
    parser.add_argument("--dbt-user", default="SAI_REVENUEOS_DBT_SVC")
    args = parser.parse_args()

    loader_token = _required_secret("Loader PAT")
    dbt_token = _required_secret("dbt PAT")
    document = {
        "account": args.account.strip(),
        "warehouse": "SAI_REVENUEOS_XS",
        "database": "SAI_REVENUEOS",
        "raw_schema": "RAW",
        "staging_schema": "STAGING",
        "profiles": {
            "loader": {
                "user": args.loader_user,
                "token": loader_token,
                "role": "SAI_REVENUEOS_LOADER",
            },
            "dbt": {
                "user": args.dbt_user,
                "token": dbt_token,
                "role": "SAI_REVENUEOS_DBT",
            },
        },
    }

    path = credential_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
    finally:
        os.chmod(path, 0o600)
    print("Snowflake credentials stored securely at %s" % path)
    print("Permissions: 600; tokens were not displayed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
