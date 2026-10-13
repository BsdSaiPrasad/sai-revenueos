"""Coordinate P1.7 inputs, P1.2 identity control, and P1.4 survivorship."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sai_revenueos_authority import AuthorityStore, FieldChange
from sai_revenueos_identity import IDENTITY_STEWARD, RESOLUTION_WRITER, IdentityStore

from .errors import (
    ResolutionAuthorizationError,
    ResolutionConflictError,
    SimulatedResolutionFailure,
    StaleReviewError,
)
from .matcher import DeterministicMatcher
from .models import ApprovalResult, CandidateMatch, ResolutionResult, StagedIdentityRecord, candidate_tuple
from .policy import ResolutionPolicy
from .store import ResolutionStore, utc_now


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _payload_value(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


class ResolutionService:
    """Run explainable matches while leaving authority in P1.2 and P1.4.

    The service proposes evidence and opens review work. It never activates a
    crosswalk until an explicitly authorized steward calls :meth:`approve`.
    """

    def __init__(
        self,
        identity_store: IdentityStore,
        resolution_store: ResolutionStore,
        policy: Optional[ResolutionPolicy] = None,
    ) -> None:
        self.identity = identity_store
        self.store = resolution_store
        self.policy = policy or ResolutionPolicy()
        self.matcher = DeterministicMatcher(self.policy)

    def _context(self, records: Iterable[StagedIdentityRecord]) -> List[Dict[str, Any]]:
        context = []
        for record in records:
            mapping = self.identity.active_mapping_for_source(record.source_record_id)
            context.append({
                "record": record.fingerprint_payload(),
                "canonical_entity_id": None if mapping is None else mapping["canonical_entity_id"],
                "mapping_status": None if mapping is None else mapping["mapping_status"],
            })
        return sorted(context, key=lambda item: (
            str(item["record"]["entity_type"]), str(item["record"]["source_record_id"])
        ))

    def _stored_result(self, run_id: str, replayed: bool) -> ResolutionResult:
        run = self.store.get_run(run_id)
        rows = self.store.candidates_for_run(run_id)
        candidates = [
            CandidateMatch(
                canonical_entity_id=row["canonical_entity_id"],
                score=float(row["score"]),
                reference_source_record_id=row["reference_source_record_id"],
                features=row["features"],
            )
            for row in rows
        ]
        reviews = self.store.reviews_for_source(run["source_record_id"])
        review_id = next((row["review_id"] for row in reviews if row["run_id"] == run_id), None)
        return ResolutionResult(
            run_id=run_id,
            source_record_id=run["source_record_id"],
            outcome=str(run["outcome"]),
            candidates=candidate_tuple(candidates),
            review_id=review_id,
            replayed=replayed,
        )

    def _existing_proposals(self, source_record_id: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for review in self.store.reviews_for_source(source_record_id):
            for candidate_id in review["candidate_evidence_ids"]:
                candidate = self.identity.get("candidate_evidence", "candidate_evidence_id", candidate_id)
                if candidate["disposition"] == "proposed":
                    result[str(candidate["candidate_canonical_id"])] = str(candidate_id)
        return result

    def resolve(
        self,
        source: StagedIdentityRecord,
        records: Iterable[StagedIdentityRecord],
        simulate_failure: bool = False,
    ) -> ResolutionResult:
        """Evaluate one latest staged record and open version-locked human review."""
        snapshot = tuple(records)
        registered = self.identity.get_source_record(source.source_record_id)
        if registered["source_system"].casefold() != source.source_system:
            raise ResolutionConflictError("staged source system does not match P1.2 SourceRecord")
        current = self.identity.active_mapping_for_source(source.source_record_id)
        candidates = [] if current is not None else self.matcher.match(source, snapshot, self.identity)
        fingerprint = _hash({
            "policy_version": self.policy.contract_version,
            "source": source.fingerprint_payload(),
            "context": self._context(snapshot),
        })
        run_id = "p18_run_%s" % fingerprint[:32]
        prior = self.store.start_run(
            run_id, fingerprint, source.source_record_id, source.event_id,
            source.entity_type, self.policy.contract_version,
            {"staging_model": source.staging_model, "candidate_scores": [
                {"canonical_entity_id": candidate.canonical_entity_id,
                 "score": candidate.score, "features": dict(candidate.features)}
                for candidate in candidates
            ]},
        )
        if prior["status"] == "completed":
            return self._stored_result(run_id, replayed=True)

        if current is not None:
            case = self.identity.resolution_case_for_source(source.source_record_id)
            self.store.finalize_run(
                run_id, "already_resolved", (), {}, int(case["version"]),
                self.policy.review_owner_role,
            )
            return self._stored_result(run_id, replayed=False)

        existing = self._existing_proposals(source.source_record_id)
        candidate_evidence_ids: Dict[str, str] = {}
        try:
            for candidate in candidates:
                candidate_id = existing.get(candidate.canonical_entity_id)
                if candidate_id is None:
                    key = "p18-propose-%s" % _hash([run_id, candidate.canonical_entity_id])[:32]
                    candidate_id = self.identity.propose_candidate(
                        source.source_record_id,
                        candidate.canonical_entity_id,
                        "deterministic_feature_evidence",
                        "p18://resolution-run/%s" % run_id,
                        candidate.score,
                        "p18_deterministic_%s" % source.entity_type.casefold(),
                        self.policy.contract_version,
                        "p1.8-resolution-engine",
                        RESOLUTION_WRITER,
                        key,
                    )
                candidate_evidence_ids[candidate.canonical_entity_id] = candidate_id

            case = self.identity.resolution_case_for_source(source.source_record_id)
            if case["status"] != "pending_review":
                self.identity.request_manual_review(
                    source.source_record_id,
                    "P1.8 requires human approval for every new crosswalk",
                    "p1.8-resolution-engine",
                    RESOLUTION_WRITER,
                    "p18-review-%s" % run_id,
                )
            if simulate_failure:
                raise SimulatedResolutionFailure("simulated failure before run finalization")
        except Exception as exc:
            self.store.fail_run(run_id, type(exc).__name__)
            raise

        outcome = "pending_review"
        if len(candidates) == 1:
            outcome = "candidate"
        elif len(candidates) > 1:
            outcome = "ambiguous"
        self.store.mark_other_pending_reviews_stale(
            source.source_record_id, run_id, "newer staged evidence created a new resolution run"
        )
        case = self.identity.resolution_case_for_source(source.source_record_id)
        self.store.finalize_run(
            run_id, outcome, candidates, candidate_evidence_ids, int(case["version"]),
            self.policy.review_owner_role,
        )
        return self._stored_result(run_id, replayed=False)

    def approve(
        self,
        review_id: str,
        candidate_evidence_id: str,
        actor_id: str,
        authority: str,
        reason: str,
        simulate_failure_after_decision: bool = False,
    ) -> ApprovalResult:
        """Apply a human decision and activate its P1.2 crosswalk idempotently."""
        if authority != IDENTITY_STEWARD:
            raise ResolutionAuthorizationError("p1_identity_steward authority is required")
        review = self.store.get_review(review_id)
        if review["status"] == "approved":
            return ApprovalResult(
                review_id, str(review["selected_candidate_evidence_id"]),
                str(review["resulting_crosswalk_id"]), True,
            )
        if review["status"] != "pending":
            raise ResolutionConflictError("identity review is no longer pending")
        if candidate_evidence_id not in review["candidate_evidence_ids"]:
            raise ResolutionConflictError("selected candidate is not part of this review")
        candidate = self.identity.get(
            "candidate_evidence", "candidate_evidence_id", candidate_evidence_id
        )
        case = self.identity.resolution_case_for_source(review["source_record_id"])
        recovering = candidate["disposition"] == "accepted" and candidate["reviewed_by"] == actor_id
        if not recovering and int(case["version"]) != int(review["expected_case_version"]):
            self.store.mark_review_stale(
                review_id, actor_id, "resolution case changed after this review was opened"
            )
            raise StaleReviewError("review is stale because newer identity evidence exists")
        if candidate["disposition"] == "proposed":
            self.identity.decide_candidate(
                candidate_evidence_id, "accepted", reason, actor_id, IDENTITY_STEWARD,
                "p18-decide-%s" % review_id,
            )
        elif not recovering:
            raise ResolutionConflictError("candidate already has a different final decision")
        if simulate_failure_after_decision:
            raise SimulatedResolutionFailure("simulated failure after candidate decision")
        crosswalk_id = self.identity.activate_mapping(
            candidate_evidence_id, actor_id, IDENTITY_STEWARD,
            "p18-activate-%s" % review_id,
        )
        self.store.decide_review(
            review_id, "approved", candidate_evidence_id, crosswalk_id, actor_id, reason
        )
        return ApprovalResult(review_id, candidate_evidence_id, crosswalk_id, recovering)

    def apply_survivorship(
        self,
        canonical_entity_id: str,
        records: Iterable[StagedIdentityRecord],
        authority_store: AuthorityStore,
    ) -> List[Any]:
        """Send mapped, governed values through the unchanged P1.4 policy engine."""
        proposals: List[Tuple[int, str, StagedIdentityRecord, Mapping[str, Any], Any]] = []
        for record in records:
            mapping = self.identity.active_mapping_for_source(record.source_record_id)
            if (
                mapping is None
                or mapping["canonical_entity_id"] != canonical_entity_id
                or record.event_type != "upsert"
                or record.is_deleted
            ):
                continue
            for extractor in self.policy.extractors_for(record.entity_type, record.source_system):
                value = _payload_value(record.raw_payload, extractor["payload_path"])
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                field = authority_store.policy.field(record.entity_type, extractor["field_name"])
                authoritative = record.source_system in field.authoritative_sources
                proposals.append((0 if authoritative else 1, record.source_updated_at or "",
                                  record, extractor, value))
        results = []
        for _, _, record, extractor, value in sorted(
            proposals, key=lambda item: (item[0], item[1], item[2].event_id)
        ):
            change = FieldChange(
                change_id="p18_survivor_%s" % _hash([
                    record.event_id, canonical_entity_id, extractor["field_name"], value
                ])[:32],
                canonical_entity_type=record.entity_type,
                canonical_entity_id=canonical_entity_id,
                field_name=str(extractor["field_name"]),
                proposed_value=value,
                source_system=record.source_system,
                source_record_id=record.source_record_id,
                source_event_id=record.event_id,
                observed_at=record.observed_at or record.source_updated_at or utc_now(),
                actor_id="p1.8-survivorship",
                actor_role="source_processor",
                evidence={
                    "kind": "p1.7_dbt_staging",
                    "staging_model": record.staging_model,
                    "event_id": record.event_id,
                    "payload_sha256": record.payload_sha256,
                    "trace_id": record.trace_id,
                    "resolution_policy_version": self.policy.contract_version,
                },
            )
            results.append(authority_store.apply_change(change, self.identity))
        return results

    def approved_mapping_output(self, generated_at: Optional[str] = None) -> Dict[str, Any]:
        """Publish only active human-approved Account/Person mappings for P1.9."""
        mappings = []
        fields = (
            "external_identity_crosswalk_id", "source_record_id", "canonical_entity_type",
            "canonical_entity_id", "mapping_status", "mapping_method", "confidence",
            "valid_from", "valid_to", "reviewed_by", "reviewed_at",
        )
        for row in self.identity.list_active_mappings(("Account", "Person")):
            mappings.append({name: row[name] for name in fields})
        return {
            "contract_name": "identity-resolution-output",
            "contract_version": "1.0.0",
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mappings": mappings,
        }
