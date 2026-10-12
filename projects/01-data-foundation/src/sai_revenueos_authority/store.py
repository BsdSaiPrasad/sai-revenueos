"""Transactional P1.4 field authority, conflict review, and audit reference.

The store accepts source proposals only after P1.2 has registered their canonical
and source identities. It preserves accepted values, conflicting proposals,
review decisions, and write-back authorization without calling an external API.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from sai_revenueos_identity import IdentityStore, uuid7
from sai_revenueos_identity.errors import (
    AuthorizationError,
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    ValidationError,
)
from sai_revenueos_sources import SourceEvent

from .policy import AuthorityPolicy, FieldPolicy


DATA_STEWARD = "data_steward"


def _utc_now() -> str:
    """Return a sortable Coordinated Universal Time timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_text(name: str, value: Any) -> str:
    """Return trimmed text or reject a missing audit attribute."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be a non-empty string" % name)
    return value.strip()


def _json(value: Any) -> str:
    """Create stable JSON while rejecting values that cannot be audited safely."""
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("value must be valid JSON") from exc


def _hash(document: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(document).encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    """Create a local operational identifier without adding a canonical entity."""
    return "%s_%s" % (prefix, uuid7())


@dataclass(frozen=True)
class FieldChange:
    """One source-backed proposal to change a governed canonical field."""

    change_id: str
    canonical_entity_type: str
    canonical_entity_id: str
    field_name: str
    proposed_value: Any
    source_system: str
    source_record_id: str
    source_event_id: str
    observed_at: str
    actor_id: str
    actor_role: str
    evidence: Mapping[str, Any]

    @classmethod
    def from_source_event(
        cls,
        event: SourceEvent,
        source_record_id: str,
        canonical_entity_type: str,
        canonical_entity_id: str,
        field_name: str,
        proposed_value: Any,
        change_id: str,
        actor_id: str = "p1.4-policy-processor",
        actor_role: str = "source_processor",
    ) -> "FieldChange":
        """Build a proposal whose evidence points to a validated P1.3 event."""
        return cls(
            change_id=change_id,
            canonical_entity_type=canonical_entity_type,
            canonical_entity_id=canonical_entity_id,
            field_name=field_name,
            proposed_value=proposed_value,
            source_system=event.source_system,
            source_record_id=source_record_id,
            source_event_id=event.event_id,
            observed_at=event.observed_at,
            actor_id=actor_id,
            actor_role=actor_role,
            evidence={
                "kind": "p1.3_source_event",
                "event_id": event.event_id,
                "payload_sha256": event.payload_sha256,
                "trace_id": event.trace_id,
            },
        )

    def as_dict(self) -> Dict[str, Any]:
        """Return the complete immutable request used for idempotency."""
        return {
            "change_id": self.change_id,
            "canonical_entity_type": self.canonical_entity_type,
            "canonical_entity_id": self.canonical_entity_id,
            "field_name": self.field_name,
            "proposed_value": self.proposed_value,
            "source_system": self.source_system.casefold(),
            "source_record_id": self.source_record_id,
            "source_event_id": self.source_event_id,
            "observed_at": self.observed_at,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ApplyResult:
    """Describe the durable result of evaluating one field proposal."""

    change_id: str
    status: str
    reason: str
    field_revision: Optional[int]
    conflict_id: Optional[str]
    replayed: bool


@dataclass(frozen=True)
class WriteBackDecision:
    """Record write-back permission; P1.4 never performs network delivery."""

    request_id: str
    status: str
    reason: str
    network_delivery: bool
    replayed: bool


class AuthorityStore:
    """Evaluate field ownership and preserve human-governed conflict history."""

    def __init__(self, database: str = ":memory:", policy: Optional[AuthorityPolicy] = None) -> None:
        self.database = database
        self.policy = policy or AuthorityPolicy()
        self._connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "AuthorityStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterable[sqlite3.Cursor]:
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

    @staticmethod
    def _audit(
        cur: sqlite3.Cursor,
        event_type: str,
        actor_id: str,
        actor_role: str,
        subject_type: str,
        subject_id: str,
        details: Mapping[str, Any],
        at: str,
    ) -> None:
        cur.execute(
            "INSERT INTO authority_audit_event VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_new_id("p14_audit"), event_type, actor_id, actor_role, subject_type,
             subject_id, _json(details), at),
        )

    @staticmethod
    def _review_event(
        cur: sqlite3.Cursor,
        conflict_id: str,
        action: str,
        from_status: Optional[str],
        to_status: str,
        actor_id: str,
        actor_role: str,
        reason: str,
        details: Mapping[str, Any],
        at: str,
    ) -> str:
        event_id = _new_id("p14_review")
        cur.execute(
            "INSERT INTO conflict_review_event VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, conflict_id, action, from_status, to_status, actor_id, actor_role,
             reason, _json(details), at),
        )
        return event_id

    @staticmethod
    def _append_history(
        cur: sqlite3.Cursor,
        change: FieldChange,
        prior_value_json: Optional[str],
        value_json: str,
        action: str,
        manual_verified: bool,
        actor_id: str,
        at: str,
    ) -> None:
        cur.execute(
            "INSERT INTO field_value_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _new_id("p14_value"), change.canonical_entity_type, change.canonical_entity_id,
                change.field_name, prior_value_json, value_json, action, change.source_system.casefold(),
                change.source_record_id, change.source_event_id, _json(dict(change.evidence)),
                int(manual_verified), actor_id, at,
            ),
        )

    @staticmethod
    def _result(row: sqlite3.Row, replayed: bool) -> ApplyResult:
        return ApplyResult(
            change_id=row["change_id"],
            status=row["outcome"],
            reason=row["reason"],
            field_revision=row["field_revision"],
            conflict_id=row["conflict_id"],
            replayed=replayed,
        )

    @staticmethod
    def _record_attempt(
        cur: sqlite3.Cursor,
        change: FieldChange,
        request_hash: str,
        status: str,
        reason: str,
        at: str,
        revision: Optional[int] = None,
        conflict_id: Optional[str] = None,
    ) -> ApplyResult:
        cur.execute(
            "INSERT INTO field_change_attempt VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (change.change_id, request_hash, _json(change.as_dict()), status, conflict_id,
             revision, reason, at),
        )
        return ApplyResult(change.change_id, status, reason, revision, conflict_id, False)

    def _validate_change(
        self, change: FieldChange, identity_store: IdentityStore
    ) -> FieldPolicy:
        for name in (
            "change_id", "canonical_entity_type", "canonical_entity_id", "field_name",
            "source_system", "source_record_id", "source_event_id", "observed_at",
            "actor_id", "actor_role",
        ):
            _require_text(name, getattr(change, name))
        _json(change.proposed_value)
        _json(dict(change.evidence))
        field = self.policy.field(change.canonical_entity_type, change.field_name)
        identity = identity_store.get_canonical_identity(change.canonical_entity_id)
        if identity["entity_type"] != change.canonical_entity_type:
            raise ValidationError("canonical entity type does not match its P1.2 identity")
        if identity["identity_status"] != "active":
            raise ConflictError("retired canonical identities cannot receive field changes")
        source = identity_store.get_source_record(change.source_record_id)
        if source["source_system"].casefold() != change.source_system.casefold():
            raise ValidationError("source system does not match the P1.2 SourceRecord")
        return field

    def _open_conflict(
        self,
        cur: sqlite3.Cursor,
        change: FieldChange,
        current: sqlite3.Row,
        field: FieldPolicy,
        reason: str,
        at: str,
    ) -> str:
        conflict_id = _new_id("p14_conflict")
        cur.execute(
            "INSERT INTO field_conflict VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conflict_id, change.canonical_entity_type, change.canonical_entity_id,
                change.field_name, current["value_json"], current["source_system"],
                current["revision"], _json(change.proposed_value), change.source_system.casefold(),
                change.source_record_id, change.source_event_id, _json(dict(change.evidence)),
                "open", field.review_owner_role, None, at, None, None, None,
            ),
        )
        self._review_event(
            cur, conflict_id, "opened", None, "open", change.actor_id, change.actor_role,
            reason, {"change_id": change.change_id, "owner_role": field.review_owner_role}, at,
        )
        self._audit(
            cur, "field_conflict_opened", change.actor_id, change.actor_role,
            "FieldConflict", conflict_id,
            {"change_id": change.change_id, "reason": reason}, at,
        )
        return conflict_id

    def apply_change(self, change: FieldChange, identity_store: IdentityStore) -> ApplyResult:
        """Evaluate one proposal without overwriting protected or conflicting truth.

        A first value or same-source update may be accepted when both the source and
        actor are authorized. A different source, a non-authoritative source, or a
        manually verified current value creates a human-owned conflict. Exact
        replays return the original outcome; changed content under one change ID is
        rejected.
        """
        field = self._validate_change(change, identity_store)
        request_hash = _hash(change.as_dict())
        at = _utc_now()
        with self._transaction() as cur:
            prior = cur.execute(
                "SELECT * FROM field_change_attempt WHERE change_id=?", (change.change_id,)
            ).fetchone()
            if prior is not None:
                if prior["request_hash"] != request_hash:
                    raise IdempotencyConflictError("change_id was reused with different content")
                return self._result(prior, replayed=True)

            current = cur.execute(
                "SELECT * FROM canonical_field_state WHERE canonical_entity_type=? "
                "AND canonical_entity_id=? AND field_name=?",
                (change.canonical_entity_type, change.canonical_entity_id, change.field_name),
            ).fetchone()
            value_json = _json(change.proposed_value)

            if change.actor_role not in field.allowed_writer_roles:
                reason = "actor role is not authorized to propose this field"
                self._audit(cur, "field_change_denied", change.actor_id, change.actor_role,
                            change.canonical_entity_type, change.canonical_entity_id,
                            {"field_name": change.field_name, "reason": reason}, at)
                return self._record_attempt(cur, change, request_hash, "denied", reason, at)

            authoritative = change.source_system.casefold() in field.authoritative_sources
            if not authoritative:
                conflict_id = None
                if current is not None and current["value_json"] != value_json:
                    conflict_id = self._open_conflict(
                        cur, change, current, field,
                        "source is not authoritative for this field", at,
                    )
                reason = "source is not authoritative for this field"
                self._audit(cur, "field_change_denied", change.actor_id, change.actor_role,
                            change.canonical_entity_type, change.canonical_entity_id,
                            {"field_name": change.field_name, "reason": reason,
                             "conflict_id": conflict_id}, at)
                return self._record_attempt(
                    cur, change, request_hash, "denied", reason, at,
                    None if current is None else current["revision"], conflict_id,
                )

            if current is None:
                cur.execute(
                    "INSERT INTO canonical_field_state VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, 1, ?)",
                    (change.canonical_entity_type, change.canonical_entity_id, change.field_name,
                     value_json, change.source_system.casefold(), change.source_record_id,
                     change.source_event_id, _json(dict(change.evidence)), at),
                )
                self._append_history(cur, change, None, value_json, "initial_value", False,
                                     change.actor_id, at)
                self._audit(cur, "field_value_applied", change.actor_id, change.actor_role,
                            change.canonical_entity_type, change.canonical_entity_id,
                            {"field_name": change.field_name, "revision": 1}, at)
                return self._record_attempt(
                    cur, change, request_hash, "applied", "authoritative initial value", at, 1
                )

            if current["value_json"] == value_json:
                reason = "proposal matches the current trusted value"
                self._audit(cur, "field_value_unchanged", change.actor_id, change.actor_role,
                            change.canonical_entity_type, change.canonical_entity_id,
                            {"field_name": change.field_name, "revision": current["revision"]}, at)
                return self._record_attempt(
                    cur, change, request_hash, "unchanged", reason, at, current["revision"]
                )

            same_source = (
                current["source_system"] == change.source_system.casefold()
                and current["source_record_id"] == change.source_record_id
            )
            if not current["manual_verified"] and same_source:
                revision = current["revision"] + 1
                cur.execute(
                    "UPDATE canonical_field_state SET value_json=?, source_event_id=?, evidence_json=?, "
                    "revision=?, updated_at=? WHERE canonical_entity_type=? AND canonical_entity_id=? "
                    "AND field_name=?",
                    (value_json, change.source_event_id, _json(dict(change.evidence)), revision, at,
                     change.canonical_entity_type, change.canonical_entity_id, change.field_name),
                )
                self._append_history(cur, change, current["value_json"], value_json,
                                     "source_update", False, change.actor_id, at)
                self._audit(cur, "field_value_applied", change.actor_id, change.actor_role,
                            change.canonical_entity_type, change.canonical_entity_id,
                            {"field_name": change.field_name, "revision": revision}, at)
                return self._record_attempt(
                    cur, change, request_hash, "applied", "authoritative same-source update",
                    at, revision,
                )

            reason = (
                "current value is manually verified"
                if current["manual_verified"] and field.protect_manual_verification
                else "different authoritative sources disagree"
            )
            conflict_id = self._open_conflict(cur, change, current, field, reason, at)
            return self._record_attempt(
                cur, change, request_hash, "review_required", reason, at,
                current["revision"], conflict_id,
            )

    def verify_current_value(
        self,
        canonical_entity_type: str,
        canonical_entity_id: str,
        field_name: str,
        actor_id: str,
        actor_role: str,
        evidence: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Mark the current value as human-verified and append provenance history."""
        field = self.policy.field(canonical_entity_type, field_name)
        actor_id = _require_text("actor_id", actor_id)
        actor_role = _require_text("actor_role", actor_role)
        if actor_role not in {DATA_STEWARD, field.review_owner_role}:
            raise AuthorizationError("assigned review owner or data_steward role is required")
        at = _utc_now()
        with self._transaction() as cur:
            current = cur.execute(
                "SELECT * FROM canonical_field_state WHERE canonical_entity_type=? "
                "AND canonical_entity_id=? AND field_name=?",
                (canonical_entity_type, canonical_entity_id, field_name),
            ).fetchone()
            if current is None:
                raise NotFoundError("canonical field state was not found")
            revision = current["revision"] + 1
            cur.execute(
                "UPDATE canonical_field_state SET manual_verified=1, verified_by=?, revision=?, "
                "updated_at=? WHERE canonical_entity_type=? AND canonical_entity_id=? AND field_name=?",
                (actor_id, revision, at, canonical_entity_type, canonical_entity_id, field_name),
            )
            synthetic = FieldChange(
                change_id=_new_id("p14_verify"), canonical_entity_type=canonical_entity_type,
                canonical_entity_id=canonical_entity_id, field_name=field_name,
                proposed_value=json.loads(current["value_json"]),
                source_system=current["source_system"], source_record_id=current["source_record_id"] or "manual",
                source_event_id=current["source_event_id"] or "manual", observed_at=at,
                actor_id=actor_id, actor_role=actor_role, evidence=evidence,
            )
            self._append_history(cur, synthetic, current["value_json"], current["value_json"],
                                 "manual_verification", True, actor_id, at)
            self._audit(cur, "field_value_manually_verified", actor_id, actor_role,
                        canonical_entity_type, canonical_entity_id,
                        {"field_name": field_name, "revision": revision,
                         "evidence": dict(evidence)}, at)
            return self.current_value(canonical_entity_type, canonical_entity_id, field_name)

    @staticmethod
    def _authorize_reviewer(conflict: sqlite3.Row, actor_id: str, actor_role: str) -> None:
        if actor_role != DATA_STEWARD and actor_role != conflict["assigned_owner_role"]:
            raise AuthorizationError("assigned conflict owner or data_steward role is required")
        if (conflict["assigned_owner_id"] is not None
                and actor_id != conflict["assigned_owner_id"]
                and actor_role != DATA_STEWARD):
            raise AuthorizationError("conflict is assigned to another reviewer")

    def assign_conflict(
        self, conflict_id: str, owner_id: str, actor_id: str, actor_role: str, reason: str
    ) -> Dict[str, Any]:
        """Assign an open conflict to a named human while preserving queue ownership."""
        owner_id = _require_text("owner_id", owner_id)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        at = _utc_now()
        with self._transaction() as cur:
            conflict = cur.execute("SELECT * FROM field_conflict WHERE conflict_id=?", (conflict_id,)).fetchone()
            if conflict is None:
                raise NotFoundError("field conflict was not found")
            if conflict["status"] not in {"open", "escalated"}:
                raise ConflictError("resolved conflict cannot be assigned")
            self._authorize_reviewer(conflict, actor_id, actor_role)
            cur.execute("UPDATE field_conflict SET assigned_owner_id=? WHERE conflict_id=?",
                        (owner_id, conflict_id))
            self._review_event(cur, conflict_id, "assigned", conflict["status"], conflict["status"],
                               actor_id, actor_role, reason, {"owner_id": owner_id}, at)
            self._audit(cur, "field_conflict_assigned", actor_id, actor_role,
                        "FieldConflict", conflict_id, {"owner_id": owner_id}, at)
        return self.get_conflict(conflict_id)

    def escalate_conflict(
        self,
        conflict_id: str,
        new_owner_role: str,
        actor_id: str,
        actor_role: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Move an unresolved case to another human-owned review queue."""
        new_owner_role = _require_text("new_owner_role", new_owner_role)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        at = _utc_now()
        with self._transaction() as cur:
            conflict = cur.execute("SELECT * FROM field_conflict WHERE conflict_id=?", (conflict_id,)).fetchone()
            if conflict is None:
                raise NotFoundError("field conflict was not found")
            if conflict["status"] not in {"open", "escalated"}:
                raise ConflictError("resolved conflict cannot be escalated")
            self._authorize_reviewer(conflict, actor_id, actor_role)
            cur.execute(
                "UPDATE field_conflict SET status='escalated', assigned_owner_role=?, "
                "assigned_owner_id=NULL WHERE conflict_id=?", (new_owner_role, conflict_id),
            )
            self._review_event(cur, conflict_id, "escalated", conflict["status"], "escalated",
                               actor_id, actor_role, reason,
                               {"new_owner_role": new_owner_role}, at)
            self._audit(cur, "field_conflict_escalated", actor_id, actor_role,
                        "FieldConflict", conflict_id,
                        {"new_owner_role": new_owner_role, "reason": reason}, at)
        return self.get_conflict(conflict_id)

    def resolve_conflict(
        self,
        conflict_id: str,
        decision: str,
        reason: str,
        reviewer_id: str,
        reviewer_role: str,
    ) -> Dict[str, Any]:
        """Approve the proposed value or keep the current value through human review."""
        if decision not in {"approve_proposed", "keep_current"}:
            raise ValidationError("decision must be approve_proposed or keep_current")
        reviewer_id = _require_text("reviewer_id", reviewer_id)
        reviewer_role = _require_text("reviewer_role", reviewer_role)
        reason = _require_text("reason", reason)
        at = _utc_now()
        with self._transaction() as cur:
            conflict = cur.execute("SELECT * FROM field_conflict WHERE conflict_id=?", (conflict_id,)).fetchone()
            if conflict is None:
                raise NotFoundError("field conflict was not found")
            if conflict["status"] not in {"open", "escalated"}:
                raise ConflictError("field conflict has already been resolved")
            self._authorize_reviewer(conflict, reviewer_id, reviewer_role)
            current = cur.execute(
                "SELECT * FROM canonical_field_state WHERE canonical_entity_type=? "
                "AND canonical_entity_id=? AND field_name=?",
                (conflict["canonical_entity_type"], conflict["canonical_entity_id"],
                 conflict["field_name"]),
            ).fetchone()
            if (current is None or current["value_json"] != conflict["current_value_json"]
                    or current["revision"] != conflict["current_revision"]):
                raise ConflictError("canonical value changed after this conflict opened")

            approved = decision == "approve_proposed"
            value_json = conflict["proposed_value_json"] if approved else current["value_json"]
            source_system = conflict["proposed_source_system"] if approved else current["source_system"]
            source_record_id = conflict["proposed_source_record_id"] if approved else current["source_record_id"]
            source_event_id = conflict["proposed_source_event_id"] if approved else current["source_event_id"]
            evidence_json = conflict["evidence_json"] if approved else current["evidence_json"]
            revision = current["revision"] + 1
            cur.execute(
                "UPDATE canonical_field_state SET value_json=?, source_system=?, source_record_id=?, "
                "source_event_id=?, evidence_json=?, manual_verified=1, verified_by=?, revision=?, "
                "updated_at=? WHERE canonical_entity_type=? AND canonical_entity_id=? AND field_name=?",
                (value_json, source_system, source_record_id, source_event_id, evidence_json,
                 reviewer_id, revision, at, conflict["canonical_entity_type"],
                 conflict["canonical_entity_id"], conflict["field_name"]),
            )
            status = "approved" if approved else "rejected"
            cur.execute(
                "UPDATE field_conflict SET status=?, resolved_at=?, reviewed_by=?, resolution_reason=? "
                "WHERE conflict_id=?", (status, at, reviewer_id, reason, conflict_id),
            )
            synthetic = FieldChange(
                change_id=_new_id("p14_resolution"),
                canonical_entity_type=conflict["canonical_entity_type"],
                canonical_entity_id=conflict["canonical_entity_id"],
                field_name=conflict["field_name"],
                proposed_value=json.loads(value_json), source_system=source_system,
                source_record_id=source_record_id or "manual",
                source_event_id=source_event_id or "manual", observed_at=at,
                actor_id=reviewer_id, actor_role=reviewer_role,
                evidence={"conflict_id": conflict_id, "resolution_reason": reason},
            )
            self._append_history(
                cur, synthetic, current["value_json"], value_json,
                "conflict_approved" if approved else "conflict_rejected", True,
                reviewer_id, at,
            )
            self._review_event(cur, conflict_id, status, conflict["status"], status,
                               reviewer_id, reviewer_role, reason,
                               {"field_revision": revision}, at)
            self._audit(cur, "field_conflict_resolved", reviewer_id, reviewer_role,
                        "FieldConflict", conflict_id,
                        {"decision": decision, "field_revision": revision}, at)
        return self.current_value(
            conflict["canonical_entity_type"], conflict["canonical_entity_id"],
            conflict["field_name"],
        )

    def evaluate_write_back(
        self,
        request_id: str,
        canonical_entity_type: str,
        canonical_entity_id: str,
        field_name: str,
        target_system: str,
        value: Any,
        actor_id: str,
        actor_role: str,
        approval_reference: Optional[str],
    ) -> WriteBackDecision:
        """Authorize or deny a write-back request without sending it anywhere."""
        request_id = _require_text("request_id", request_id)
        target_system = _require_text("target_system", target_system).casefold()
        actor_id = _require_text("actor_id", actor_id)
        actor_role = _require_text("actor_role", actor_role)
        field = self.policy.field(canonical_entity_type, field_name)
        value_json = _json(value)
        payload = {
            "request_id": request_id, "canonical_entity_type": canonical_entity_type,
            "canonical_entity_id": canonical_entity_id, "field_name": field_name,
            "target_system": target_system, "value": value, "actor_id": actor_id,
            "actor_role": actor_role, "approval_reference": approval_reference,
        }
        request_hash = _hash(payload)
        at = _utc_now()
        with self._transaction() as cur:
            prior = cur.execute(
                "SELECT * FROM write_back_request WHERE request_id=?", (request_id,)
            ).fetchone()
            if prior is not None:
                if prior["request_hash"] != request_hash:
                    raise IdempotencyConflictError("request_id was reused with different content")
                return WriteBackDecision(request_id, prior["status"], prior["reason"], False, True)
            current = cur.execute(
                "SELECT * FROM canonical_field_state WHERE canonical_entity_type=? "
                "AND canonical_entity_id=? AND field_name=?",
                (canonical_entity_type, canonical_entity_id, field_name),
            ).fetchone()
            status = "authorized"
            reason = "authorized for downstream delivery by a separate service"
            if current is None:
                status, reason = "denied", "canonical field has no trusted current value"
            elif actor_role not in self.policy.write_back_authorized_roles:
                status, reason = "denied", "actor role lacks write-back authority"
            elif target_system not in field.write_back_targets:
                status, reason = "denied", "target system is not approved for this field"
            elif current["value_json"] != value_json:
                status, reason = "denied", "write-back value does not match canonical truth"
            elif self.policy.requires_resolved_conflict:
                approval = None
                if approval_reference:
                    approval = cur.execute(
                        "SELECT * FROM field_conflict WHERE conflict_id=?", (approval_reference,)
                    ).fetchone()
                if (approval is None or approval["status"] not in {"approved", "rejected"}
                        or approval["canonical_entity_type"] != canonical_entity_type
                        or approval["canonical_entity_id"] != canonical_entity_id
                        or approval["field_name"] != field_name):
                    status, reason = "denied", "resolved conflict approval is required"
            cur.execute(
                "INSERT INTO write_back_request VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (request_id, request_hash, canonical_entity_type, canonical_entity_id,
                 field_name, target_system, value_json, actor_id, actor_role,
                 approval_reference, status, reason, at),
            )
            self._audit(cur, "write_back_%s" % status, actor_id, actor_role,
                        canonical_entity_type, canonical_entity_id,
                        {"field_name": field_name, "target_system": target_system,
                         "request_id": request_id, "reason": reason}, at)
            return WriteBackDecision(request_id, status, reason, False, False)

    def current_value(
        self, canonical_entity_type: str, canonical_entity_id: str, field_name: str
    ) -> Dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM canonical_field_state WHERE canonical_entity_type=? "
            "AND canonical_entity_id=? AND field_name=?",
            (canonical_entity_type, canonical_entity_id, field_name),
        ).fetchone()
        if row is None:
            raise NotFoundError("canonical field state was not found")
        result = dict(row)
        result["value"] = json.loads(result.pop("value_json"))
        result["evidence"] = json.loads(result.pop("evidence_json"))
        result["manual_verified"] = bool(result["manual_verified"])
        return result

    def get_conflict(self, conflict_id: str) -> Dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM field_conflict WHERE conflict_id=?", (conflict_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("field conflict was not found")
        result = dict(row)
        result["current_value"] = json.loads(result.pop("current_value_json"))
        result["proposed_value"] = json.loads(result.pop("proposed_value_json"))
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

    def value_history(
        self, canonical_entity_type: str, canonical_entity_id: str, field_name: str
    ) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM field_value_history WHERE canonical_entity_type=? "
            "AND canonical_entity_id=? AND field_name=? ORDER BY recorded_at, history_id",
            (canonical_entity_type, canonical_entity_id, field_name),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["prior_value"] = (
                None if item["prior_value_json"] is None else json.loads(item["prior_value_json"])
            )
            item["value"] = json.loads(item["value_json"])
            item["evidence"] = json.loads(item["evidence_json"])
            del item["prior_value_json"]
            del item["value_json"]
            del item["evidence_json"]
            item["manual_verified"] = bool(item["manual_verified"])
            result.append(item)
        return result

    def review_history(self, conflict_id: str) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM conflict_review_event WHERE conflict_id=? "
            "ORDER BY recorded_at, review_event_id", (conflict_id,)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def audit_history(self) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM authority_audit_event ORDER BY recorded_at, audit_event_id"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def count(self, table: str) -> int:
        allowed = {
            "canonical_field_state", "field_value_history", "field_conflict",
            "conflict_review_event", "field_change_attempt", "write_back_request",
            "authority_audit_event",
        }
        if table not in allowed:
            raise ValidationError("unsupported table")
        return int(self._connection.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])


__all__ = [
    "ApplyResult", "AuthorityStore", "DATA_STEWARD", "FieldChange", "WriteBackDecision",
]
