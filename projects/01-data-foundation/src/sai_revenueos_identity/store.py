"""Transactional SQLite reference implementation for P1.2 identity control."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .errors import (
    AuthorizationError,
    ConflictError,
    IdempotencyConflictError,
    InvalidTransitionError,
    NotFoundError,
    SimulatedFailure,
    ValidationError,
)
from .ids import PREFIX_REGISTRY, PrefixedIDGenerator, validate_prefixed_id
from .normalization import normalize_source_identity


IDENTITY_WRITER = "p1_identity_writer"
SOURCE_WRITER = "p1_source_writer"
RESOLUTION_WRITER = "p1_resolution_writer"
IDENTITY_STEWARD = "p1_identity_steward"

CANONICAL_TARGET_TYPES = frozenset(
    {
        "Account", "Person", "Opportunity", "Activity", "Campaign", "Quote",
        "Contract", "Order", "Subscription", "Invoice", "ProductUser", "SupportCase",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("%s must be a non-empty string" % name)
    return value.strip()


def _require_authority(actual: str, required: str) -> None:
    if actual != required:
        raise AuthorizationError("%s authority is required" % required)


def _request_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class IdentityStore:
    """Small, explicit reference service; not a production persistence layer."""

    _ID_LOCATIONS = {
        "SourceRecord": ("source_record", "source_record_id"),
        "SourceObservation": ("source_observation", "source_observation_id"),
        "ResolutionCase": ("resolution_case", "resolution_case_id"),
        "CandidateEvidence": ("candidate_evidence", "candidate_evidence_id"),
        "ExternalIdentityCrosswalk": ("external_identity_crosswalk", "external_identity_crosswalk_id"),
        "IdentityMergeEvent": ("identity_merge_event", "merge_event_id"),
        "AuditEvent": ("audit_event", "audit_event_id"),
    }

    def __init__(self, database: str = ":memory:", id_generator: Optional[PrefixedIDGenerator] = None) -> None:
        self.database = database
        self._ids = id_generator or PrefixedIDGenerator()
        self._connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self._connection.executescript(schema)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "IdentityStore":
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

    def _new_id(self, cursor: sqlite3.Cursor, entity_type: str) -> str:
        location = self._ID_LOCATIONS.get(entity_type)
        if location is None:
            location = ("canonical_identity", "canonical_id")
        table, column = location
        return self._ids.generate(
            entity_type,
            lambda value: cursor.execute(
                "SELECT 1 FROM %s WHERE %s = ?" % (table, column), (value,)
            ).fetchone() is not None,
        )

    def _claim_operation(
        self, cursor: sqlite3.Cursor, key: str, operation: str, payload: Mapping[str, Any], now: str
    ) -> Optional[Tuple[str, str]]:
        key = _require_text("idempotency_key", key)
        digest = _request_hash(payload)
        existing = cursor.execute(
            "SELECT * FROM idempotency_operation WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if existing is not None:
            if existing["operation_type"] != operation or existing["request_hash"] != digest:
                raise IdempotencyConflictError("idempotency key was already used for a different request")
            if existing["status"] == "completed":
                return existing["result_type"], existing["result_id"]
            raise ConflictError("idempotent operation is already in progress")
        cursor.execute(
            "INSERT INTO idempotency_operation VALUES (?, ?, ?, NULL, NULL, 'in_progress', ?, NULL)",
            (key, operation, digest, now),
        )
        return None

    @staticmethod
    def _complete_operation(
        cursor: sqlite3.Cursor, key: str, result_type: str, result_id: str, now: str
    ) -> None:
        cursor.execute(
            "UPDATE idempotency_operation SET result_type=?, result_id=?, status='completed', completed_at=? "
            "WHERE idempotency_key=?", (result_type, result_id, now, key),
        )

    def _audit(
        self, cursor: sqlite3.Cursor, event_type: str, actor_id: str, subject_type: str,
        subject_id: str, operation_key: Optional[str], details: Mapping[str, Any], now: str,
    ) -> str:
        audit_id = self._new_id(cursor, "AuditEvent")
        cursor.execute(
            "INSERT INTO audit_event VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (audit_id, event_type, actor_id, subject_type, subject_id, operation_key, now,
             json.dumps(details, sort_keys=True, separators=(",", ":"))),
        )
        return audit_id

    @staticmethod
    def _row(cursor: sqlite3.Cursor, sql: str, values: Tuple[Any, ...], label: str) -> sqlite3.Row:
        row = cursor.execute(sql, values).fetchone()
        if row is None:
            raise NotFoundError("%s was not found" % label)
        return row

    def get(self, table: str, id_column: str, value: str) -> Dict[str, Any]:
        allowed = {
            "canonical_identity": "canonical_id", "source_record": "source_record_id",
            "source_observation": "source_observation_id", "resolution_case": "resolution_case_id",
            "candidate_evidence": "candidate_evidence_id",
            "external_identity_crosswalk": "external_identity_crosswalk_id",
            "identity_merge_event": "merge_event_id", "audit_event": "audit_event_id",
        }
        if allowed.get(table) != id_column:
            raise ValidationError("unsupported lookup")
        row = self._connection.execute(
            "SELECT * FROM %s WHERE %s = ?" % (table, id_column), (value,)
        ).fetchone()
        if row is None:
            raise NotFoundError("record was not found")
        return dict(row)

    def count(self, table: str) -> int:
        allowed = {
            "canonical_identity", "source_record", "source_observation", "resolution_case",
            "candidate_evidence", "external_identity_crosswalk", "identity_merge_event",
            "merge_mapping_change", "audit_event", "idempotency_operation",
        }
        if table not in allowed:
            raise ValidationError("unsupported table")
        return int(self._connection.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])

    def create_canonical_identity(
        self, entity_type: str, actor_id: str, authority: str, idempotency_key: str,
        at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, IDENTITY_WRITER)
        if entity_type not in CANONICAL_TARGET_TYPES:
            raise ValidationError("entity type is not a P1.2 crosswalk target")
        actor_id = _require_text("actor_id", actor_id)
        now = at or _utc_now()
        payload = {"entity_type": entity_type, "actor_id": actor_id}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "create_canonical_identity", payload, now)
            if prior:
                return prior[1]
            canonical_id = self._new_id(cur, entity_type)
            cur.execute(
                "INSERT INTO canonical_identity VALUES (?, ?, 'active', NULL, ?, NULL)",
                (canonical_id, entity_type, now),
            )
            self._audit(cur, "canonical_identity_created", actor_id, entity_type, canonical_id,
                        idempotency_key, {"entity_type": entity_type}, now)
            self._complete_operation(cur, idempotency_key, entity_type, canonical_id, now)
            return canonical_id

    def get_or_create_source_record(
        self, source_system: str, source_tenant: str, source_object_type: str,
        source_object_id: str, observation_key: str, actor_id: str, authority: str,
        record_fingerprint: Optional[str] = None, payload_reference: Optional[str] = None,
        observed_at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, SOURCE_WRITER)
        actor_id = _require_text("actor_id", actor_id)
        observation_key = _require_text("observation_key", observation_key)
        identity = normalize_source_identity(
            source_system, source_tenant, source_object_type, source_object_id
        )
        now = observed_at or _utc_now()
        key_values = (
            identity.normalized_source_system, identity.normalized_source_tenant,
            identity.normalized_source_object_type, identity.normalized_source_object_id,
        )
        with self._transaction() as cur:
            source = cur.execute(
                "SELECT * FROM source_record WHERE normalized_source_system=? AND "
                "normalized_source_tenant=? AND normalized_source_object_type=? AND "
                "normalized_source_object_id=?", key_values,
            ).fetchone()
            if source is None:
                source_id = self._new_id(cur, "SourceRecord")
                cur.execute(
                    "INSERT INTO source_record VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (source_id, identity.source_system, identity.source_tenant,
                     identity.source_object_type, identity.source_object_id, *key_values, now, now),
                )
                case_id = self._new_id(cur, "ResolutionCase")
                cur.execute(
                    "INSERT INTO resolution_case VALUES (?, ?, 'unresolved', 0, NULL, 1, ?, ?)",
                    (case_id, source_id, now, now),
                )
                self._audit(cur, "source_record_created", actor_id, "SourceRecord", source_id,
                            observation_key, {"resolution_case_id": case_id}, now)
            else:
                source_id = source["source_record_id"]
                cur.execute(
                    "UPDATE source_record SET last_observed_at=CASE WHEN last_observed_at<? THEN ? "
                    "ELSE last_observed_at END WHERE source_record_id=?", (now, now, source_id)
                )
            observation = cur.execute(
                "SELECT source_record_id FROM source_observation WHERE observation_key=?",
                (observation_key,),
            ).fetchone()
            if observation is not None:
                if observation["source_record_id"] != source_id:
                    raise ConflictError("observation key belongs to another source record")
                return source_id
            observation_id = self._new_id(cur, "SourceObservation")
            cur.execute(
                "INSERT INTO source_observation VALUES (?, ?, ?, ?, ?, ?)",
                (observation_id, source_id, observation_key, now, record_fingerprint, payload_reference),
            )
            return source_id

    def propose_candidate(
        self, source_record_id: str, candidate_canonical_id: str, evidence_type: str,
        evidence_reference: str, confidence: float, method: str, policy_version: str,
        actor_id: str, authority: str, idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, RESOLUTION_WRITER)
        actor_id = _require_text("actor_id", actor_id)
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValidationError("confidence must be between 0 and 1")
        now = at or _utc_now()
        payload = {"source_record_id": source_record_id, "candidate_canonical_id": candidate_canonical_id,
                   "evidence_type": evidence_type, "evidence_reference": evidence_reference,
                   "confidence": float(confidence), "method": method, "policy_version": policy_version}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "propose_candidate", payload, now)
            if prior:
                return prior[1]
            case = self._row(cur, "SELECT * FROM resolution_case WHERE source_record_id=?",
                             (source_record_id,), "resolution case")
            target = self._row(cur, "SELECT * FROM canonical_identity WHERE canonical_id=?",
                               (candidate_canonical_id,), "canonical identity")
            if target["identity_status"] != "active":
                raise ConflictError("candidate canonical identity is retired")
            if case["status"] in ("resolved", "ambiguous"):
                raise InvalidTransitionError("case must be reopened for review before adding candidates")
            candidate_id = self._new_id(cur, "CandidateEvidence")
            cur.execute(
                "INSERT INTO candidate_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, NULL, NULL, NULL, ?)",
                (candidate_id, case["resolution_case_id"], candidate_canonical_id,
                 _require_text("evidence_type", evidence_type), _require_text("evidence_reference", evidence_reference),
                 float(confidence), _require_text("method", method), _require_text("policy_version", policy_version),
                 now, idempotency_key),
            )
            proposed = cur.execute(
                "SELECT COUNT(*) FROM candidate_evidence WHERE resolution_case_id=? AND disposition='proposed'",
                (case["resolution_case_id"],),
            ).fetchone()[0]
            new_status = "ambiguous" if proposed > 1 else "candidate"
            cur.execute(
                "UPDATE resolution_case SET status=?, review_required=?, reason=?, version=version+1, updated_at=? "
                "WHERE resolution_case_id=?",
                (new_status, int(new_status == "ambiguous"), "multiple candidates" if proposed > 1 else None,
                 now, case["resolution_case_id"]),
            )
            self._audit(cur, "candidate_proposed", actor_id, "CandidateEvidence", candidate_id,
                        idempotency_key, payload, now)
            self._complete_operation(cur, idempotency_key, "CandidateEvidence", candidate_id, now)
            return candidate_id

    def request_manual_review(
        self, source_record_id: str, reason: str, actor_id: str, authority: str,
        idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, RESOLUTION_WRITER)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        now = at or _utc_now()
        payload = {"source_record_id": source_record_id, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "request_manual_review", payload, now)
            if prior:
                return prior[1]
            case = self._row(cur, "SELECT * FROM resolution_case WHERE source_record_id=?",
                             (source_record_id,), "resolution case")
            if case["status"] == "pending_review":
                raise InvalidTransitionError("case is already pending review")
            try:
                cur.execute(
                    "UPDATE resolution_case SET status='pending_review', review_required=1, reason=?, "
                    "version=version+1, updated_at=? WHERE resolution_case_id=?",
                    (reason, now, case["resolution_case_id"]),
                )
            except sqlite3.IntegrityError as exc:
                raise InvalidTransitionError(str(exc)) from exc
            self._audit(cur, "manual_review_requested", actor_id, "ResolutionCase",
                        case["resolution_case_id"], idempotency_key, payload, now)
            self._complete_operation(cur, idempotency_key, "ResolutionCase", case["resolution_case_id"], now)
            return case["resolution_case_id"]

    def decide_candidate(
        self, candidate_evidence_id: str, decision: str, reason: str, actor_id: str,
        authority: str, idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        if decision not in ("accepted", "rejected"):
            raise ValidationError("decision must be accepted or rejected")
        now = at or _utc_now()
        payload = {"candidate_evidence_id": candidate_evidence_id, "decision": decision, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "decide_candidate", payload, now)
            if prior:
                return prior[1]
            candidate = self._row(cur, "SELECT * FROM candidate_evidence WHERE candidate_evidence_id=?",
                                  (candidate_evidence_id,), "candidate evidence")
            if candidate["disposition"] != "proposed":
                raise InvalidTransitionError("candidate already has a final disposition")
            case = self._row(cur, "SELECT * FROM resolution_case WHERE resolution_case_id=?",
                             (candidate["resolution_case_id"],), "resolution case")
            if case["status"] == "ambiguous":
                raise InvalidTransitionError("ambiguous cases must enter pending_review before a decision")
            cur.execute(
                "UPDATE candidate_evidence SET disposition=?, reviewed_by=?, reviewed_at=?, decision_reason=? "
                "WHERE candidate_evidence_id=?",
                (decision, actor_id, now, reason, candidate_evidence_id),
            )
            case_id = candidate["resolution_case_id"]
            if decision == "accepted":
                cur.execute(
                    "UPDATE candidate_evidence SET disposition='expired', reviewed_by=?, reviewed_at=?, "
                    "decision_reason='another candidate was accepted' WHERE resolution_case_id=? "
                    "AND disposition='proposed' AND candidate_evidence_id<>?",
                    (actor_id, now, case_id, candidate_evidence_id),
                )
                next_status, review = "resolved", 0
            else:
                remaining = cur.execute(
                    "SELECT COUNT(*) FROM candidate_evidence WHERE resolution_case_id=? AND disposition='proposed'",
                    (case_id,),
                ).fetchone()[0]
                # A reviewed ambiguous case stays in the human-review lane while
                # any undecided alternative remains; it never silently becomes a
                # single automatic candidate after a steward rejects one option.
                next_status, review = (("pending_review", 1) if remaining >= 1 else ("no_match", 0))
            try:
                cur.execute(
                    "UPDATE resolution_case SET status=?, review_required=?, reason=?, version=version+1, updated_at=? "
                    "WHERE resolution_case_id=?",
                    (next_status, review, reason, now, case_id),
                )
            except sqlite3.IntegrityError as exc:
                raise InvalidTransitionError(str(exc)) from exc
            self._audit(cur, "candidate_%s" % decision, actor_id, "CandidateEvidence",
                        candidate_evidence_id, idempotency_key, payload, now)
            self._complete_operation(cur, idempotency_key, "CandidateEvidence", candidate_evidence_id, now)
            return candidate_evidence_id

    def _insert_active_mapping(
        self, cur: sqlite3.Cursor, source_id: str, canonical_id: str, mapping_method: str,
        confidence: float, actor_id: str, now: str, supersedes: Optional[str] = None,
        correction_reason: Optional[str] = None,
    ) -> str:
        target = self._row(cur, "SELECT * FROM canonical_identity WHERE canonical_id=?",
                           (canonical_id,), "canonical identity")
        xwalk_id = self._new_id(cur, "ExternalIdentityCrosswalk")
        cur.execute(
            "INSERT INTO external_identity_crosswalk VALUES (?, ?, ?, ?, 'active', ?, ?, ?, NULL, ?, ?, ?, ?, ?)",
            (xwalk_id, source_id, target["entity_type"], canonical_id, mapping_method,
             float(confidence), now, supersedes, actor_id, now, correction_reason, now),
        )
        return xwalk_id

    def activate_mapping(
        self, candidate_evidence_id: str, actor_id: str, authority: str,
        idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        now = at or _utc_now()
        payload = {"candidate_evidence_id": candidate_evidence_id}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "activate_mapping", payload, now)
            if prior:
                return prior[1]
            candidate = self._row(
                cur, "SELECT ce.*, rc.source_record_id, rc.status AS case_status FROM candidate_evidence ce "
                "JOIN resolution_case rc ON rc.resolution_case_id=ce.resolution_case_id "
                "WHERE ce.candidate_evidence_id=?", (candidate_evidence_id,), "candidate evidence",
            )
            if candidate["disposition"] != "accepted" or candidate["case_status"] != "resolved":
                raise ConflictError("only an accepted candidate on a resolved case can become authoritative")
            mapping_id = self._insert_active_mapping(
                cur, candidate["source_record_id"], candidate["candidate_canonical_id"],
                candidate["method"], candidate["confidence"], actor_id, now,
            )
            self._audit(cur, "crosswalk_activated", actor_id, "ExternalIdentityCrosswalk",
                        mapping_id, idempotency_key, payload, now)
            self._complete_operation(cur, idempotency_key, "ExternalIdentityCrosswalk", mapping_id, now)
            return mapping_id

    def correct_mapping(
        self, source_record_id: str, replacement_canonical_id: str, reason: str,
        actor_id: str, authority: str, idempotency_key: str, at: Optional[str] = None,
        simulate_failure: bool = False,
    ) -> str:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        now = at or _utc_now()
        payload = {"source_record_id": source_record_id,
                   "replacement_canonical_id": replacement_canonical_id, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "correct_mapping", payload, now)
            if prior:
                return prior[1]
            current = self._row(cur, "SELECT * FROM external_identity_crosswalk WHERE source_record_id=? "
                                "AND mapping_status='active'", (source_record_id,), "active crosswalk")
            if current["canonical_entity_id"] == replacement_canonical_id:
                raise ConflictError("replacement is already authoritative")
            cur.execute(
                "UPDATE external_identity_crosswalk SET mapping_status='superseded', valid_to=?, correction_reason=? "
                "WHERE external_identity_crosswalk_id=?", (now, reason,
                                                            current["external_identity_crosswalk_id"]),
            )
            if simulate_failure:
                raise SimulatedFailure("simulated failure after closing the prior mapping")
            replacement = self._insert_active_mapping(
                cur, source_record_id, replacement_canonical_id, "manual_correction",
                current["confidence"], actor_id, now, current["external_identity_crosswalk_id"], reason,
            )
            self._audit(cur, "crosswalk_corrected", actor_id, "ExternalIdentityCrosswalk",
                        replacement, idempotency_key,
                        {**payload, "superseded_crosswalk_id": current["external_identity_crosswalk_id"]}, now)
            self._complete_operation(cur, idempotency_key, "ExternalIdentityCrosswalk", replacement, now)
            return replacement

    def revoke_mapping(
        self, source_record_id: str, reason: str, actor_id: str, authority: str,
        idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        now = at or _utc_now()
        payload = {"source_record_id": source_record_id, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "revoke_mapping", payload, now)
            if prior:
                return prior[1]
            current = self._row(cur, "SELECT * FROM external_identity_crosswalk WHERE source_record_id=? "
                                "AND mapping_status='active'", (source_record_id,), "active crosswalk")
            cur.execute(
                "UPDATE external_identity_crosswalk SET mapping_status='revoked', valid_to=?, correction_reason=? "
                "WHERE external_identity_crosswalk_id=?", (now, reason,
                                                            current["external_identity_crosswalk_id"]),
            )
            case = self._row(cur, "SELECT * FROM resolution_case WHERE source_record_id=?",
                             (source_record_id,), "resolution case")
            cur.execute(
                "UPDATE resolution_case SET status='no_match', review_required=0, reason=?, version=version+1, "
                "updated_at=? WHERE resolution_case_id=?", (reason, now, case["resolution_case_id"]),
            )
            self._audit(cur, "crosswalk_revoked", actor_id, "ExternalIdentityCrosswalk",
                        current["external_identity_crosswalk_id"], idempotency_key, payload, now)
            self._complete_operation(cur, idempotency_key, "ExternalIdentityCrosswalk",
                                     current["external_identity_crosswalk_id"], now)
            return current["external_identity_crosswalk_id"]

    def merge_identities(
        self, survivor_canonical_id: str, retired_canonical_id: str, reason: str,
        actor_id: str, authority: str, idempotency_key: str, at: Optional[str] = None,
    ) -> str:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        if survivor_canonical_id == retired_canonical_id:
            raise ValidationError("survivor and retired IDs must differ")
        now = at or _utc_now()
        payload = {"survivor_canonical_id": survivor_canonical_id,
                   "retired_canonical_id": retired_canonical_id, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "merge_identities", payload, now)
            if prior:
                return prior[1]
            survivor = self._row(cur, "SELECT * FROM canonical_identity WHERE canonical_id=?",
                                 (survivor_canonical_id,), "survivor identity")
            retired = self._row(cur, "SELECT * FROM canonical_identity WHERE canonical_id=?",
                                (retired_canonical_id,), "retired identity")
            if survivor["identity_status"] != "active" or retired["identity_status"] != "active":
                raise ConflictError("both identities must be active before merge")
            if survivor["entity_type"] != retired["entity_type"]:
                raise ConflictError("only identities of the same entity type can merge")
            merge_id = self._new_id(cur, "IdentityMergeEvent")
            cur.execute(
                "INSERT INTO identity_merge_event VALUES (?, 'merge', ?, ?, NULL, ?, ?, ?, ?)",
                (merge_id, survivor_canonical_id, retired_canonical_id, now, actor_id,
                 reason, idempotency_key),
            )
            mappings = cur.execute(
                "SELECT * FROM external_identity_crosswalk WHERE canonical_entity_id=? "
                "AND mapping_status='active' ORDER BY source_record_id", (retired_canonical_id,),
            ).fetchall()
            for mapping in mappings:
                prior_id = mapping["external_identity_crosswalk_id"]
                cur.execute(
                    "UPDATE external_identity_crosswalk SET mapping_status='superseded', valid_to=?, "
                    "correction_reason=? WHERE external_identity_crosswalk_id=?",
                    (now, "identity merge: %s" % reason, prior_id),
                )
                merged_id = self._insert_active_mapping(
                    cur, mapping["source_record_id"], survivor_canonical_id, "identity_merge",
                    mapping["confidence"], actor_id, now, prior_id, reason,
                )
                cur.execute(
                    "INSERT INTO merge_mapping_change VALUES (?, ?, ?, ?)",
                    (merge_id, mapping["source_record_id"], prior_id, merged_id),
                )
            cur.execute(
                "UPDATE canonical_identity SET identity_status='retired', redirect_to_canonical_id=?, retired_at=? "
                "WHERE canonical_id=?", (survivor_canonical_id, now, retired_canonical_id),
            )
            self._audit(cur, "canonical_identities_merged", actor_id, survivor["entity_type"],
                        survivor_canonical_id, idempotency_key,
                        {**payload, "merge_event_id": merge_id, "mappings_moved": len(mappings)}, now)
            self._complete_operation(cur, idempotency_key, "IdentityMergeEvent", merge_id, now)
            return merge_id

    def unmerge_identities(
        self, root_merge_event_id: str, reason: str, actor_id: str, authority: str,
        idempotency_key: str, at: Optional[str] = None,
    ) -> Tuple[str, List[str]]:
        _require_authority(authority, IDENTITY_STEWARD)
        actor_id = _require_text("actor_id", actor_id)
        reason = _require_text("reason", reason)
        now = at or _utc_now()
        payload = {"root_merge_event_id": root_merge_event_id, "reason": reason}
        with self._transaction() as cur:
            prior = self._claim_operation(cur, idempotency_key, "unmerge_identities", payload, now)
            if prior:
                event = self._row(cur, "SELECT * FROM identity_merge_event WHERE merge_event_id=?",
                                  (prior[1],), "unmerge event")
                uncertain = json.loads(cur.execute(
                    "SELECT details_json FROM audit_event WHERE subject_id=? AND event_type='canonical_identities_unmerged'",
                    (event["merge_event_id"],),
                ).fetchone()[0])["uncertain_source_record_ids"]
                return prior[1], uncertain
            root = self._row(cur, "SELECT * FROM identity_merge_event WHERE merge_event_id=?",
                             (root_merge_event_id,), "root merge event")
            if root["event_type"] != "merge":
                raise ValidationError("root event must be a merge")
            already = cur.execute(
                "SELECT merge_event_id FROM identity_merge_event WHERE event_type='unmerge' "
                "AND root_merge_event_id=?", (root_merge_event_id,),
            ).fetchone()
            if already:
                raise ConflictError("merge has already been reversed")
            retired = self._row(cur, "SELECT * FROM canonical_identity WHERE canonical_id=?",
                                (root["retired_canonical_id"],), "retired identity")
            if retired["identity_status"] != "retired" or retired["redirect_to_canonical_id"] != root["survivor_canonical_id"]:
                raise ConflictError("retired identity no longer has the merge redirect")
            unmerge_id = self._new_id(cur, "IdentityMergeEvent")
            cur.execute(
                "INSERT INTO identity_merge_event VALUES (?, 'unmerge', ?, ?, ?, ?, ?, ?, ?)",
                (unmerge_id, root["survivor_canonical_id"], root["retired_canonical_id"],
                 root_merge_event_id, now, actor_id, reason, idempotency_key),
            )
            cur.execute(
                "UPDATE canonical_identity SET identity_status='active', redirect_to_canonical_id=NULL, retired_at=NULL "
                "WHERE canonical_id=?", (root["retired_canonical_id"],),
            )
            uncertain: List[str] = []
            changes = cur.execute(
                "SELECT * FROM merge_mapping_change WHERE merge_event_id=? ORDER BY source_record_id",
                (root_merge_event_id,),
            ).fetchall()
            for change in changes:
                active = cur.execute(
                    "SELECT * FROM external_identity_crosswalk WHERE source_record_id=? AND mapping_status='active'",
                    (change["source_record_id"],),
                ).fetchone()
                if active is None or active["external_identity_crosswalk_id"] != change["merged_crosswalk_id"]:
                    uncertain.append(change["source_record_id"])
                    case = self._row(cur, "SELECT * FROM resolution_case WHERE source_record_id=?",
                                     (change["source_record_id"],), "resolution case")
                    if case["status"] != "pending_review":
                        cur.execute(
                            "UPDATE resolution_case SET status='pending_review', review_required=1, reason=?, "
                            "version=version+1, updated_at=? WHERE resolution_case_id=?",
                            ("unmerge needs human review", now, case["resolution_case_id"]),
                        )
                    continue
                cur.execute(
                    "UPDATE external_identity_crosswalk SET mapping_status='superseded', valid_to=?, "
                    "correction_reason=? WHERE external_identity_crosswalk_id=?",
                    (now, "unmerge: %s" % reason, active["external_identity_crosswalk_id"]),
                )
                prior_mapping = self._row(
                    cur, "SELECT * FROM external_identity_crosswalk WHERE external_identity_crosswalk_id=?",
                    (change["prior_crosswalk_id"],), "pre-merge crosswalk",
                )
                self._insert_active_mapping(
                    cur, change["source_record_id"], root["retired_canonical_id"], "identity_unmerge",
                    prior_mapping["confidence"], actor_id, now, active["external_identity_crosswalk_id"], reason,
                )
            self._audit(cur, "canonical_identities_unmerged", actor_id, "IdentityMergeEvent",
                        unmerge_id, idempotency_key,
                        {**payload, "uncertain_source_record_ids": uncertain,
                         "restored_mappings": len(changes) - len(uncertain)}, now)
            self._complete_operation(cur, idempotency_key, "IdentityMergeEvent", unmerge_id, now)
            return unmerge_id, uncertain

    def active_mapping_for_source(self, source_record_id: str) -> Optional[Dict[str, Any]]:
        row = self._connection.execute(
            "SELECT * FROM external_identity_crosswalk WHERE source_record_id=? "
            "AND mapping_status='active' AND valid_to IS NULL", (source_record_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def resolution_case_for_source(self, source_record_id: str) -> Dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM resolution_case WHERE source_record_id=?", (source_record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError("resolution case was not found")
        return dict(row)

    def reconcile(self) -> List[Dict[str, str]]:
        """Return actionable invariant violations; an empty list is the healthy state."""
        checks = [
            ("active_mapping_to_retired_identity",
             "SELECT x.external_identity_crosswalk_id AS record_id FROM external_identity_crosswalk x "
             "JOIN canonical_identity c ON c.canonical_id=x.canonical_entity_id "
             "WHERE x.mapping_status='active' AND c.identity_status<>'active'"),
            ("resolved_case_without_active_mapping",
             "SELECT rc.resolution_case_id AS record_id FROM resolution_case rc WHERE rc.status='resolved' "
             "AND NOT EXISTS (SELECT 1 FROM external_identity_crosswalk x WHERE x.source_record_id=rc.source_record_id "
             "AND x.mapping_status='active')"),
            ("active_mapping_on_unresolved_case",
             "SELECT x.external_identity_crosswalk_id AS record_id FROM external_identity_crosswalk x "
             "JOIN resolution_case rc ON rc.source_record_id=x.source_record_id "
             "WHERE x.mapping_status='active' AND rc.status NOT IN ('resolved','pending_review')"),
            ("invalid_identity_redirect",
             "SELECT canonical_id AS record_id FROM canonical_identity WHERE "
             "(identity_status='active' AND redirect_to_canonical_id IS NOT NULL) OR "
             "(identity_status='retired' AND redirect_to_canonical_id IS NULL)"),
            ("review_state_without_flag",
             "SELECT resolution_case_id AS record_id FROM resolution_case WHERE "
             "status IN ('ambiguous','pending_review') AND review_required<>1"),
        ]
        issues: List[Dict[str, str]] = []
        for issue_type, sql in checks:
            for row in self._connection.execute(sql):
                issues.append({"issue_type": issue_type, "record_id": row["record_id"]})
        overlaps = self._connection.execute(
            "SELECT a.external_identity_crosswalk_id AS record_id FROM external_identity_crosswalk a "
            "JOIN external_identity_crosswalk b ON a.source_record_id=b.source_record_id "
            "AND a.external_identity_crosswalk_id<b.external_identity_crosswalk_id "
            "AND a.valid_from<COALESCE(b.valid_to,'9999-12-31T23:59:59.999999Z') "
            "AND b.valid_from<COALESCE(a.valid_to,'9999-12-31T23:59:59.999999Z')"
        ).fetchall()
        issues.extend({"issue_type": "overlapping_crosswalk_intervals", "record_id": row["record_id"]}
                      for row in overlaps)
        return issues


__all__ = [
    "IdentityStore", "IDENTITY_WRITER", "SOURCE_WRITER", "RESOLUTION_WRITER",
    "IDENTITY_STEWARD", "CANONICAL_TARGET_TYPES", "PREFIX_REGISTRY", "validate_prefixed_id",
]
