"""Create authenticated Snowflake connections from local role-restricted PATs.

Programmatic Access Tokens (PATs) let the loader and dbt use separate service
users without a reusable human password. GitHub Actions never calls this module
and receives no credentials.
"""

from __future__ import annotations

from typing import Any, Dict

from .credentials import load_snowflake_credentials

def connect_to_snowflake(role_environment: str = "SNOWFLAKE_DBT_ROLE") -> Any:
    """Open a least-privilege Snowflake session using the matching local PAT.

    Inputs:
        ``role_environment`` names the environment variable containing either
        the RAW loader role or the dbt transformation role.

    Returns:
        A Snowflake Python Connector connection with autocommit disabled.

    Failures:
        Missing configuration, unsafe file permissions, a missing connector
        package, rejected authentication, or a network problem raises an error.
    """
    try:
        import snowflake.connector  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Snowflake connector is missing; install warehouse/requirements-dbt.txt in a Python 3.12 venv"
        ) from exc

    profile = "loader" if "LOADER" in role_environment.upper() else "dbt"
    credentials = load_snowflake_credentials(profile)

    parameters: Dict[str, Any] = {
        "account": credentials["account"],
        "user": credentials["user"],
        # Snowflake's connector accepts a PAT in the password field. It is
        # supplied only in memory and is never printed or written to logs.
        "password": credentials["password"],
        "role": credentials["role"],
        "warehouse": credentials["warehouse"],
        "database": credentials["database"],
        "schema": credentials["raw_schema"],
        "application": "SAI_REVENUEOS_P17",
        "client_session_keep_alive": False,
        "session_parameters": {
            "QUERY_TAG": "sai_revenueos_p17",
            "STATEMENT_TIMEOUT_IN_SECONDS": 300,
        },
    }
    connection = snowflake.connector.connect(**parameters)
    connection.autocommit(False)
    return connection
