"""Transactional P1.3 source-event, history, replay, and checkpoint reference.

The store commits raw input before standardization, then integrates each valid
event with P1.2's public ``get_or_create_source_record`` interface. It does not
call a live vendor API, approve identity candidates, or delete canonical records.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sai_revenueos_identity import SOURCE_WRITER, IdentityStore
from sai_revenueos_identity.errors import ConflictError, NotFoundError, SimulatedFailure, ValidationError

from .contracts import CONTRACT_VERSION, SourceContractRegistry, SourceEvent, standardize_event


def _utc_now() -> str:
    """Return the timestamp format used by the local source database."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ProcessResult:
    """Describe the durable result of one source-event processing attempt."""

    event_id: str
    source_record_id: str
    processing_status: str
    became_current: bool
    replayed: bool


class SourceStore:
    """Persist raw source events, immutable history, current state, and checkpoints."""

    def __init__(self, database: str = ":memory:") -> None:
        self.database = database
        self._connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        self._contracts = SourceContractRegistry()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()

    def __enter__(self) -> "SourceStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterable[sqlite3.Cursor]:
        """Commit a local source-state change atomically or roll it back."""
        cursor = self._connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            cursor.close()

    def _persist_raw_event(self, event: SourceEvent) -> sqlite3.Row:
        """Durably preserve an immutable event before standardization starts."""
        received_at = _utc_now()
        with self._transaction() as cur:
            existing = cur.execute("SELECT * FROM source_event WHERE event_id=?", (event.event_id,)).fetchone()
            if existing is not None:
                if existing["envelope_sha256"] != event.envelope_sha256:
                    raise ConflictError("event_id was replayed with different content")
                return existing
            cur.execute(
                "INSERT INTO source_event VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', 0, NULL, NULL, NULL, NULL, ?, NULL)",
                (
                    event.event_id, event.contract_version, event.source_system, event.source_tenant,
                    event.source_object_type, event.source_object_id, event.event_type,
                    event.source_updated_at, event.observed_at, event.trace_id, event.extraction_id,
                    event.stream_name, event.checkpoint_cursor, event.checkpoint_high_watermark_at,
                    event.raw_payload_json, event.payload_sha256, event.envelope_sha256, received_at,
                ),
            )
            return cur.execute("SELECT * FROM source_event WHERE event_id=?", (event.event_id,)).fetchone()

    def _start_attempt(self, event_id: str) -> None:
        """Record that a received or failed event is being retried."""
        with self._transaction() as cur:
            cur.execute(
                "UPDATE source_event SET processing_attempts=processing_attempts+1, "
                "last_error_type=NULL, last_error_message=NULL WHERE event_id=? AND processing_status<>'processed'",
                (event_id,),
            )

    def _mark_failed(self, event_id: str, error: Exception) -> None:
        """Preserve a concise failure on the raw event without advancing its checkpoint."""
        with self._transaction() as cur:
            cur.execute(
                "UPDATE source_event SET processing_status='failed', last_error_type=?, "
                "last_error_message=? WHERE event_id=? AND processing_status<>'processed'",
                (type(error).__name__, str(error)[:1000], event_id),
            )

    @staticmethod
    def _result(row: sqlite3.Row, replayed: bool) -> ProcessResult:
        return ProcessResult(
            event_id=row["event_id"],
            source_record_id=row["source_record_id"],
            processing_status=row["processing_status"],
            became_current=bool(row["became_current"]),
            replayed=replayed,
        )

    @staticmethod
    def _is_newer(event: SourceEvent, current: Optional[sqlite3.Row]) -> bool:
        """Keep late events in history without allowing them to replace newer state."""
        if current is None:
            return True
        incoming = (event.source_updated_at, event.observed_at, event.event_id)
        existing = (current["source_updated_at"], current["observed_at"], current["latest_event_id"])
        return incoming > existing

    @staticmethod
    def _advance_checkpoint(cur: sqlite3.Cursor, event: SourceEvent, processed_at: str) -> None:
        """Advance a checkpoint only after the event's history write has succeeded."""
        existing = cur.execute(
            "SELECT * FROM connector_checkpoint WHERE source_system=? AND source_tenant=? AND stream_name=?",
            (event.source_system, event.source_tenant, event.stream_name),
        ).fetchone()
        if existing is not None and event.checkpoint_high_watermark_at < existing["high_watermark_at"]:
            return
        cur.execute(
            "INSERT INTO connector_checkpoint VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_system, source_tenant, stream_name) DO UPDATE SET "
            "contract_version=excluded.contract_version, cursor=excluded.cursor, "
            "high_watermark_at=excluded.high_watermark_at, last_event_id=excluded.last_event_id, "
            "updated_at=excluded.updated_at",
            (
                event.source_system, event.source_tenant, event.stream_name, CONTRACT_VERSION,
                event.checkpoint_cursor, event.checkpoint_high_watermark_at, event.event_id, processed_at,
            ),
        )

    def process_event(
        self,
        event: SourceEvent,
        identity_store: IdentityStore,
        actor_id: str = "p1.3-source-processor",
        simulate_failure: bool = False,
    ) -> ProcessResult:
        """Persist, standardize, and checkpoint one event with safe replay.

        Raw JSON is committed first. Essential-field validation runs next, followed
        by P1.2 source registration using ``event_id`` as the observation key. The
        immutable history row, current-state update, processed status, and checkpoint
        then commit in one local transaction.

        ``simulate_failure`` raises after the history writes but before commit. The
        raw event and P1.2 observation remain durable; retry is safe because both use
        the stable event ID, while source history and the checkpoint roll back.
        """
        received = self._persist_raw_event(event)
        if received["processing_status"] == "processed":
            return self._result(received, replayed=True)
        self._start_attempt(event.event_id)
        try:
            standardized = standardize_event(event, self._contracts)
            source_record_id = identity_store.get_or_create_source_record(
                event.source_system,
                event.source_tenant,
                event.source_object_type,
                event.source_object_id,
                event.event_id,
                actor_id,
                SOURCE_WRITER,
                record_fingerprint="sha256:%s" % event.payload_sha256,
                payload_reference="source-event:%s" % event.event_id,
                observed_at=event.observed_at,
            )
            standardized_json = json.dumps(standardized, sort_keys=True, separators=(",", ":"))
            processed_at = _utc_now()
            with self._transaction() as cur:
                stored = cur.execute("SELECT * FROM source_event WHERE event_id=?", (event.event_id,)).fetchone()
                if stored["processing_status"] == "processed":
                    return self._result(stored, replayed=True)
                cur.execute(
                    "INSERT INTO source_record_version VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id, source_record_id, event.event_type, event.source_updated_at,
                        event.observed_at, int(event.event_type == "delete"), standardized_json, processed_at,
                    ),
                )
                current = cur.execute(
                    "SELECT * FROM source_current_state WHERE source_record_id=?", (source_record_id,)
                ).fetchone()
                became_current = self._is_newer(event, current)
                if became_current:
                    cur.execute(
                        "INSERT INTO source_current_state VALUES (?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(source_record_id) DO UPDATE SET "
                        "latest_event_id=excluded.latest_event_id, source_updated_at=excluded.source_updated_at, "
                        "observed_at=excluded.observed_at, is_deleted=excluded.is_deleted, "
                        "standardized_payload_json=excluded.standardized_payload_json, updated_at=excluded.updated_at",
                        (
                            source_record_id, event.event_id, event.source_updated_at, event.observed_at,
                            int(event.event_type == "delete"), standardized_json, processed_at,
                        ),
                    )
                if simulate_failure:
                    raise SimulatedFailure("simulated P1.3 failure before history and checkpoint commit")
                cur.execute(
                    "UPDATE source_event SET processing_status='processed', source_record_id=?, "
                    "became_current=?, processed_at=?, last_error_type=NULL, last_error_message=NULL "
                    "WHERE event_id=?",
                    (source_record_id, int(became_current), processed_at, event.event_id),
                )
                self._advance_checkpoint(cur, event, processed_at)
                completed = cur.execute("SELECT * FROM source_event WHERE event_id=?", (event.event_id,)).fetchone()
                return self._result(completed, replayed=False)
        except Exception as exc:
            self._mark_failed(event.event_id, exc)
            raise

    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Return one preserved raw event and its processing state."""
        row = self._connection.execute("SELECT * FROM source_event WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            raise NotFoundError("source event was not found")
        result = dict(row)
        result["raw_payload"] = json.loads(result.pop("raw_payload_json"))
        return result

    def current_state(self, source_record_id: str) -> Dict[str, Any]:
        """Return the newest source state while retaining all older versions."""
        row = self._connection.execute(
            "SELECT * FROM source_current_state WHERE source_record_id=?", (source_record_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("current source state was not found")
        result = dict(row)
        result["standardized_payload"] = json.loads(result.pop("standardized_payload_json"))
        return result

    def history_for_source(self, source_record_id: str) -> List[Dict[str, Any]]:
        """Return immutable source versions in source-change order."""
        rows = self._connection.execute(
            "SELECT v.*, e.raw_payload_json FROM source_record_version v "
            "JOIN source_event e USING(event_id) WHERE v.source_record_id=? "
            "ORDER BY v.source_updated_at, v.observed_at, v.event_id",
            (source_record_id,),
        ).fetchall()
        history: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["standardized_payload"] = json.loads(item.pop("standardized_payload_json"))
            item["raw_payload"] = json.loads(item.pop("raw_payload_json"))
            history.append(item)
        return history

    def checkpoint(self, source_system: str, source_tenant: str, stream_name: str) -> Optional[Dict[str, Any]]:
        """Return the last durable connector checkpoint, if one exists."""
        row = self._connection.execute(
            "SELECT * FROM connector_checkpoint WHERE source_system=? AND source_tenant=? AND stream_name=?",
            (source_system.casefold(), source_tenant, stream_name),
        ).fetchone()
        return None if row is None else dict(row)

    def replay_window(
        self,
        source_system: str,
        source_tenant: str,
        stream_name: str,
        overlap_seconds: int = 300,
    ) -> Optional[Dict[str, Any]]:
        """Return the inclusive replay boundary before the saved high watermark."""
        if not isinstance(overlap_seconds, int) or isinstance(overlap_seconds, bool) or overlap_seconds < 0:
            raise ValidationError("overlap_seconds must be a non-negative integer")
        checkpoint = self.checkpoint(source_system, source_tenant, stream_name)
        if checkpoint is None:
            return None
        high = datetime.fromisoformat(checkpoint["high_watermark_at"].replace("Z", "+00:00"))
        replay_from = (high - timedelta(seconds=overlap_seconds)).astimezone(timezone.utc)
        return {
            **checkpoint,
            "overlap_seconds": overlap_seconds,
            "replay_from": replay_from.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        }

    def count(self, table: str) -> int:
        """Count allowlisted source rows for tests and the local demonstration."""
        allowed = {"source_event", "source_record_version", "source_current_state", "connector_checkpoint"}
        if table not in allowed:
            raise ValidationError("unsupported table")
        return int(self._connection.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])
