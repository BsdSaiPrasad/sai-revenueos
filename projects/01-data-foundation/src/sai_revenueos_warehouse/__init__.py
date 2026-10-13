"""P1.7 Snowflake RAW loading interfaces.

The package copies immutable P1.3/P1.6 source events into Snowflake without
changing their identifiers, payloads, timestamps, or processing evidence. dbt
owns normalization after the RAW load.
"""

from .connection import connect_to_snowflake
from .credentials import credential_path, dbt_environment, load_snowflake_credentials
from .loader import LoadConflictError, LoadResult, SourceEventRow, load_source_events, read_source_events

__all__ = [
    "LoadConflictError",
    "LoadResult",
    "SourceEventRow",
    "connect_to_snowflake",
    "credential_path",
    "dbt_environment",
    "load_snowflake_credentials",
    "load_source_events",
    "read_source_events",
]
