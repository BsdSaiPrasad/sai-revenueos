"""Idempotently copy P1.3/P1.6 SQLite source history into Snowflake RAW.

The loader treats ``event_id`` as the immutable event key. An exact replay is a
no-op. Reusing an event ID with a different envelope hash fails the complete
batch before any RAW row is committed.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SOURCE_COLUMNS = (
    "event_id",
    "contract_version",
    "source_system",
    "source_tenant",
    "source_object_type",
    "source_object_id",
    "event_type",
    "source_updated_at",
    "observed_at",
    "trace_id",
    "extraction_id",
    "stream_name",
    "checkpoint_cursor",
    "checkpoint_high_watermark_at",
    "raw_payload_json",
    "payload_sha256",
    "envelope_sha256",
    "processing_status",
    "processing_attempts",
    "last_error_type",
    "last_error_message",
    "source_record_id",
    "became_current",
    "received_at",
    "processed_at",
)


class LoadConflictError(RuntimeError):
    """Raised when an event ID already exists with different immutable content."""


@dataclass(frozen=True)
class SourceEventRow:
    """One complete SQLite source event ready for a Snowflake RAW batch."""

    values: Tuple[Any, ...]

    @property
    def event_id(self) -> str:
        return str(self.values[0])


@dataclass(frozen=True)
class LoadResult:
    """Summarize one atomic RAW load without exposing source payloads."""

    selected: int
    inserted: int
    replayed: int
    before_count: int
    after_count: int


def _qualified_table(database: str, schema: str, table: str) -> str:
    for value in (database, schema, table):
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("unsafe Snowflake identifier: %s" % value)
    return "%s.%s.%s" % (database.upper(), schema.upper(), table.upper())


def read_source_events(database_path: Path, limit: Optional[int] = None) -> List[SourceEventRow]:
    """Read immutable source events in their original local arrival order.

    The function reads every processing state, including failed raw events, so
    Snowflake RAW remains evidence-preserving. ``limit`` is intended only for a
    controlled demonstration and always selects the earliest events.
    """
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError("source history database was not found: %s" % path)
    query = "SELECT %s FROM source_event ORDER BY received_at, event_id" % ", ".join(_SOURCE_COLUMNS)
    parameters: Sequence[Any] = ()
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be positive")
        query += " LIMIT ?"
        parameters = (limit,)
    with sqlite3.connect(str(path)) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [SourceEventRow(tuple(row)) for row in rows]


def _scalar(cursor: Any, sql: str) -> int:
    cursor.execute(sql)
    row = cursor.fetchone()
    return int(row[0])


def load_source_events(
    connection: Any,
    rows: Iterable[SourceEventRow],
    database: str = "SAI_REVENUEOS",
    raw_schema: str = "RAW",
) -> LoadResult:
    """Atomically merge a batch into ``RAW.SOURCE_EVENT``.

    Exact ``event_id`` replays are counted and ignored. A conflicting envelope
    hash rolls back the batch, protecting immutable source history. The caller
    owns authentication and closes the connection.
    """
    batch = list(rows)
    target = _qualified_table(database, raw_schema, "SOURCE_EVENT")
    temporary = _qualified_table(database, raw_schema, "P17_SOURCE_EVENT_LOAD")
    cursor = connection.cursor()
    try:
        before_count = _scalar(cursor, "SELECT COUNT(*) FROM %s" % target)
        if not batch:
            return LoadResult(0, 0, 0, before_count, before_count)

        cursor.execute(
            "CREATE OR REPLACE TEMPORARY TABLE %s (" % temporary
            + "EVENT_ID VARCHAR NOT NULL, CONTRACT_VERSION VARCHAR NOT NULL, "
            "SOURCE_SYSTEM VARCHAR NOT NULL, SOURCE_TENANT VARCHAR NOT NULL, "
            "SOURCE_OBJECT_TYPE VARCHAR NOT NULL, SOURCE_OBJECT_ID VARCHAR NOT NULL, "
            "EVENT_TYPE VARCHAR NOT NULL, SOURCE_UPDATED_AT VARCHAR NOT NULL, "
            "OBSERVED_AT VARCHAR NOT NULL, TRACE_ID VARCHAR NOT NULL, EXTRACTION_ID VARCHAR NOT NULL, "
            "STREAM_NAME VARCHAR NOT NULL, CHECKPOINT_CURSOR VARCHAR NOT NULL, "
            "CHECKPOINT_HIGH_WATERMARK_AT VARCHAR NOT NULL, RAW_PAYLOAD_JSON VARCHAR NOT NULL, "
            "PAYLOAD_SHA256 VARCHAR NOT NULL, ENVELOPE_SHA256 VARCHAR NOT NULL, "
            "PROCESSING_STATUS VARCHAR NOT NULL, PROCESSING_ATTEMPTS NUMBER NOT NULL, "
            "LAST_ERROR_TYPE VARCHAR, LAST_ERROR_MESSAGE VARCHAR, SOURCE_RECORD_ID VARCHAR, "
            "BECAME_CURRENT BOOLEAN, RECEIVED_AT VARCHAR NOT NULL, PROCESSED_AT VARCHAR)"
        )
        placeholders = ", ".join(["%s"] * len(_SOURCE_COLUMNS))
        cursor.executemany(
            "INSERT INTO %s (%s) VALUES (%s)"
            % (temporary, ", ".join(name.upper() for name in _SOURCE_COLUMNS), placeholders),
            [row.values for row in batch],
        )

        cursor.execute(
            "SELECT S.EVENT_ID FROM %s S JOIN %s T ON T.EVENT_ID=S.EVENT_ID "
            "WHERE T.ENVELOPE_SHA256<>S.ENVELOPE_SHA256 LIMIT 1" % (temporary, target)
        )
        conflict = cursor.fetchone()
        if conflict is not None:
            raise LoadConflictError("event_id has different immutable content: %s" % conflict[0])

        existing = _scalar(
            cursor,
            "SELECT COUNT(*) FROM %s S JOIN %s T ON T.EVENT_ID=S.EVENT_ID" % (temporary, target),
        )
        target_columns = ", ".join(name.upper() for name in _SOURCE_COLUMNS)
        source_values = []
        for name in _SOURCE_COLUMNS:
            if name == "raw_payload_json":
                source_values.append("PARSE_JSON(S.RAW_PAYLOAD_JSON)")
            else:
                source_values.append("S.%s" % name.upper())
        cursor.execute(
            "MERGE INTO %s T USING %s S ON T.EVENT_ID=S.EVENT_ID "
            "WHEN NOT MATCHED THEN INSERT (%s, LOAD_BATCH_ID) VALUES (%s, UUID_STRING())"
            % (target, temporary, target_columns, ", ".join(source_values))
        )
        after_count = _scalar(cursor, "SELECT COUNT(*) FROM %s" % target)
        connection.commit()
        inserted = len(batch) - existing
        return LoadResult(len(batch), inserted, existing, before_count, after_count)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
