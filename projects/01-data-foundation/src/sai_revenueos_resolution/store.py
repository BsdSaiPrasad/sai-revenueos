"""Durable P1.8 match-run and manual-review evidence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sai_revenueos_identity import uuid7

from .errors import ResolutionConflictError
from .models import CandidateMatch


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid7())


class ResolutionStore:
    """Store explainable runs and review work without duplicating crosswalk truth."""

    def __init__(self, database: str = ":memory:") -> None:
        self.database = database
        self._connection = sqlite3.connect(database, isolation_level=None, timeout=5.0)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if database != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ResolutionStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterable[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()
        finally:
            cursor.close()

    def _audit(
        self, cursor: sqlite3.Cursor, event_type: str, subject_type: str,
        subject_id: str, actor_id: str, details: Mapping[str, Any], at: str,
    ) -> None:
        cursor.execute(
            "INSERT INTO resolution_audit_event VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_id("p18_audit"), event_type, subject_type, subject_id, actor_id, at, _json(details)),
        )

    def start_run(
        self, run_id: str, fingerprint: str, source_record_id: str,
        source_event_id: str, entity_type: str, policy_version: str,
        evidence: Mapping[str, Any], at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create one processing run or return its safe retry target."""
        now = at or utc_now()
        with self._transaction() as cur:
            prior = cur.execute(
                "SELECT * FROM resolution_run WHERE input_fingerprint=?", (fingerprint,)
            ).fetchone()
            if prior is not None:
                if prior["run_id"] != run_id:
                    raise ResolutionConflictError("resolution fingerprint maps to another run")
                return dict(prior)
            cur.execute(
                "INSERT INTO resolution_run VALUES (?, ?, ?, ?, ?, ?, 'processing', NULL, 0, ?, NULL, ?, NULL)",
                (run_id, fingerprint, source_record_id, source_event_id, entity_type,
                 policy_version, _json(dict(evidence)), now),
            )
            self._audit(cur, "resolution_started", "ResolutionRun", run_id,
                        "p1.8-resolution-engine", {"source_record_id": source_record_id}, now)
        return self.get_run(run_id)

    def fail_run(self, run_id: str, error_code: str, at: Optional[str] = None) -> None:
        now = at or utc_now()
        with self._transaction() as cur:
            cur.execute(
                "UPDATE resolution_run SET status='failed', error_code=?, completed_at=? WHERE run_id=?",
                (error_code, now, run_id),
            )
            self._audit(cur, "resolution_failed", "ResolutionRun", run_id,
                        "p1.8-resolution-engine", {"error_code": error_code}, now)

    def finalize_run(
        self, run_id: str, outcome: str, candidates: Sequence[CandidateMatch],
        candidate_evidence_ids: Mapping[str, str], case_version: int,
        owner_role: str, at: Optional[str] = None,
    ) -> Optional[str]:
        """Commit candidate evidence references and one version-locked review item."""
        now = at or utc_now()
        with self._transaction() as cur:
            prior = cur.execute("SELECT status FROM resolution_run WHERE run_id=?", (run_id,)).fetchone()
            if prior is None:
                raise ResolutionConflictError("resolution run was not started")
            if prior["status"] == "completed":
                review = cur.execute(
                    "SELECT review_id FROM identity_review_work_item WHERE run_id=?", (run_id,)
                ).fetchone()
                return None if review is None else str(review["review_id"])
            for rank, candidate in enumerate(candidates, 1):
                cur.execute(
                    "INSERT INTO match_candidate_result VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_id, candidate.canonical_entity_id, candidate.score, rank,
                     candidate.reference_source_record_id, _json(dict(candidate.features)),
                     candidate_evidence_ids.get(candidate.canonical_entity_id)),
                )
            cur.execute(
                "UPDATE resolution_run SET status='completed', outcome=?, candidate_count=?, "
                "error_code=NULL, completed_at=? WHERE run_id=?",
                (outcome, len(candidates), now, run_id),
            )
            review_id: Optional[str] = None
            if outcome != "already_resolved":
                review_id = _id("p18_review")
                evidence_ids = [
                    candidate_evidence_ids[candidate.canonical_entity_id]
                    for candidate in candidates
                    if candidate.canonical_entity_id in candidate_evidence_ids
                ]
                cur.execute(
                    "INSERT INTO identity_review_work_item VALUES (?, ?, "
                    "(SELECT source_record_id FROM resolution_run WHERE run_id=?), ?, ?, ?, NULL, "
                    "'pending', NULL, NULL, ?, NULL, NULL, NULL)",
                    (review_id, run_id, run_id, _json(evidence_ids), case_version, owner_role, now),
                )
                self._audit(cur, "identity_review_opened", "IdentityReview", review_id,
                            "p1.8-resolution-engine",
                            {"run_id": run_id, "candidate_count": len(candidates),
                             "expected_case_version": case_version}, now)
            self._audit(cur, "resolution_completed", "ResolutionRun", run_id,
                        "p1.8-resolution-engine", {"outcome": outcome}, now)
            return review_id

    def mark_other_pending_reviews_stale(
        self, source_record_id: str, except_run_id: str, reason: str,
        at: Optional[str] = None,
    ) -> None:
        now = at or utc_now()
        with self._transaction() as cur:
            rows = cur.execute(
                "SELECT review_id FROM identity_review_work_item WHERE source_record_id=? "
                "AND run_id<>? AND status='pending'", (source_record_id, except_run_id),
            ).fetchall()
            for row in rows:
                cur.execute(
                    "UPDATE identity_review_work_item SET status='stale', decided_at=?, "
                    "decision_reason=? WHERE review_id=?", (now, reason, row["review_id"]),
                )
                self._audit(cur, "identity_review_stale", "IdentityReview", row["review_id"],
                            "p1.8-resolution-engine", {"reason": reason}, now)

    def decide_review(
        self, review_id: str, status: str, selected_candidate_id: Optional[str],
        crosswalk_id: Optional[str], actor_id: str, reason: str,
        at: Optional[str] = None,
    ) -> None:
        now = at or utc_now()
        with self._transaction() as cur:
            current = cur.execute(
                "SELECT status FROM identity_review_work_item WHERE review_id=?", (review_id,)
            ).fetchone()
            if current is None:
                raise ResolutionConflictError("identity review was not found")
            if current["status"] == status:
                return
            if current["status"] != "pending":
                raise ResolutionConflictError("identity review is no longer pending")
            cur.execute(
                "UPDATE identity_review_work_item SET status=?, selected_candidate_evidence_id=?, "
                "resulting_crosswalk_id=?, decided_at=?, decided_by=?, decision_reason=? "
                "WHERE review_id=?",
                (status, selected_candidate_id, crosswalk_id, now, actor_id, reason, review_id),
            )
            self._audit(cur, "identity_review_%s" % status, "IdentityReview", review_id,
                        actor_id, {"candidate_evidence_id": selected_candidate_id,
                                   "crosswalk_id": crosswalk_id, "reason": reason}, now)

    def mark_review_stale(self, review_id: str, actor_id: str, reason: str) -> None:
        self.decide_review(review_id, "stale", None, None, actor_id, reason)

    def get_run(self, run_id: str) -> Dict[str, Any]:
        row = self._connection.execute("SELECT * FROM resolution_run WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ResolutionConflictError("resolution run was not found")
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

    def candidates_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM match_candidate_result WHERE run_id=? ORDER BY rank", (run_id,)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["features"] = json.loads(item.pop("features_json"))
            result.append(item)
        return result

    def get_review(self, review_id: str) -> Dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM identity_review_work_item WHERE review_id=?", (review_id,)
        ).fetchone()
        if row is None:
            raise ResolutionConflictError("identity review was not found")
        result = dict(row)
        result["candidate_evidence_ids"] = json.loads(result.pop("candidate_evidence_ids_json"))
        return result

    def reviews_for_source(self, source_record_id: str) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT review_id FROM identity_review_work_item WHERE source_record_id=? "
            "ORDER BY created_at, review_id", (source_record_id,)
        ).fetchall()
        return [self.get_review(str(row["review_id"])) for row in rows]

    def audit_history(self) -> List[Dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM resolution_audit_event ORDER BY occurred_at, audit_event_id"
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            result.append(item)
        return result

    def count(self, table: str) -> int:
        if table not in {
            "resolution_run", "match_candidate_result", "identity_review_work_item",
            "resolution_audit_event",
        }:
            raise ValueError("unsupported table")
        return int(self._connection.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])
