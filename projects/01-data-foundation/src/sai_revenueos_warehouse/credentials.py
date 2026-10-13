"""Load P1.7 Snowflake credentials from one ignored, permission-restricted file.

The file is created interactively by ``configure_snowflake_auth.py``. Tokens
never belong in source control, shell history, command arguments, or dbt logs.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Mapping


REPO = Path(__file__).resolve().parents[4]
DEFAULT_CREDENTIAL_PATH = REPO / "generated-data/p17-snowflake/credentials.json"


def credential_path() -> Path:
    """Return the configured credential file without reading its contents."""
    override = os.environ.get("SNOWFLAKE_CREDENTIALS_FILE", "").strip()
    return Path(override).expanduser() if override else DEFAULT_CREDENTIAL_PATH


def load_snowflake_credentials(profile: str) -> Dict[str, str]:
    """Read one least-privilege Snowflake profile from the local secret file.

    Args:
        profile: ``loader`` for RAW inserts or ``dbt`` for staging builds.

    Returns:
        Connection settings including the selected service user and PAT.

    Raises:
        RuntimeError if the file is missing, readable by other local users,
        malformed, or missing a required value.
    """
    path = credential_path()
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Snowflake credentials are not configured; run configure_snowflake_auth.py"
        ) from exc
    if mode & 0o077:
        raise RuntimeError("Snowflake credential file must have permissions 600")

    try:
        document: Mapping[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        selected: Mapping[str, Any] = document["profiles"][profile]
    except (KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
        raise RuntimeError("Snowflake credential file is invalid") from exc

    values = {
        "account": str(document.get("account", "")).strip(),
        "user": str(selected.get("user", "")).strip(),
        "password": str(selected.get("token", "")).strip(),
        "role": str(selected.get("role", "")).strip(),
        "warehouse": str(document.get("warehouse", "SAI_REVENUEOS_XS")).strip(),
        "database": str(document.get("database", "SAI_REVENUEOS")).strip(),
        "raw_schema": str(document.get("raw_schema", "RAW")).strip(),
        "staging_schema": str(document.get("staging_schema", "STAGING")).strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("Snowflake credential file is missing: %s" % ", ".join(missing))
    return values


def dbt_environment(base: Mapping[str, str] | None = None) -> Dict[str, str]:
    """Return a subprocess environment for dbt without logging the PAT."""
    values = load_snowflake_credentials("dbt")
    environment = dict(base or os.environ)
    environment.update({
        "SNOWFLAKE_ACCOUNT": values["account"],
        "SNOWFLAKE_USER": values["user"],
        "SNOWFLAKE_DBT_TOKEN": values["password"],
        "SNOWFLAKE_DBT_ROLE": values["role"],
        "SNOWFLAKE_WAREHOUSE": values["warehouse"],
        "SNOWFLAKE_DATABASE": values["database"],
        "SNOWFLAKE_RAW_SCHEMA": values["raw_schema"],
        "SNOWFLAKE_STAGING_SCHEMA": values["staging_schema"],
    })
    return environment
