"""Typed inputs and outputs for P1.8 matching and review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .errors import ResolutionValidationError


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().casefold() in {"1", "true", "yes"}


@dataclass(frozen=True)
class StagedIdentityRecord:
    """One latest Account or Person record from the P1.7 staging boundary."""

    event_id: str
    source_record_id: str
    source_system: str
    source_tenant: str
    source_object_type: str
    source_object_id: str
    entity_type: str
    name: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    employer_source_object_id: Optional[str] = None
    employer_name: Optional[str] = None
    job_title: Optional[str] = None
    event_type: str = "upsert"
    is_deleted: bool = False
    source_updated_at: Optional[str] = None
    observed_at: Optional[str] = None
    trace_id: Optional[str] = None
    payload_sha256: Optional[str] = None
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    staging_model: str = ""

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "source_record_id": self.source_record_id,
            "source_system": self.source_system,
            "source_tenant": self.source_tenant,
            "source_object_type": self.source_object_type,
            "source_object_id": self.source_object_id,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ResolutionValidationError("staged record is missing: %s" % ", ".join(missing))
        if self.entity_type not in {"Account", "Person"}:
            raise ResolutionValidationError("P1.8 supports only Account and Person")
        if self.event_type not in {"upsert", "delete"}:
            raise ResolutionValidationError("event_type must be upsert or delete")

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "StagedIdentityRecord":
        """Build a record from a Snowflake row or equivalent test mapping."""
        values = {str(key).casefold(): value for key, value in row.items()}
        raw = values.get("raw_payload")
        if raw is None:
            raw = values.get("raw_payload_json") or {}
        return cls(
            event_id=str(values.get("event_id", "")),
            source_record_id=str(values.get("source_record_id", "")),
            source_system=str(values.get("source_system", "")).casefold(),
            source_tenant=str(values.get("source_tenant", "")),
            source_object_type=str(values.get("source_object_type", "")),
            source_object_id=str(values.get("source_object_id", "")),
            entity_type=str(values.get("entity_type", "")),
            name=_text(values.get("name")),
            domain=_text(values.get("domain")),
            email=_text(values.get("email")),
            country=_text(values.get("country")),
            employer_source_object_id=_text(values.get("employer_source_object_id")),
            employer_name=_text(values.get("employer_name")),
            job_title=_text(values.get("job_title")),
            event_type=str(values.get("event_type", "upsert")).casefold(),
            is_deleted=_boolean(values.get("is_deleted")),
            source_updated_at=_text(values.get("source_updated_at")),
            observed_at=_text(values.get("observed_at")),
            trace_id=_text(values.get("trace_id")),
            payload_sha256=_text(values.get("payload_sha256")),
            raw_payload=raw if isinstance(raw, Mapping) else {},
            staging_model=str(values.get("staging_model", "")),
        )

    def fingerprint_payload(self) -> Dict[str, Any]:
        """Return only deterministic fields that affect a match evaluation."""
        return {
            "event_id": self.event_id,
            "source_record_id": self.source_record_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "domain": self.domain,
            "email": self.email,
            "country": self.country,
            "employer_source_object_id": self.employer_source_object_id,
            "employer_name": self.employer_name,
            "event_type": self.event_type,
            "is_deleted": self.is_deleted,
            "payload_sha256": self.payload_sha256,
        }


@dataclass(frozen=True)
class CandidateMatch:
    """An explainable canonical candidate produced by deterministic rules."""

    canonical_entity_id: str
    score: float
    reference_source_record_id: str
    features: Mapping[str, Any]


@dataclass(frozen=True)
class ResolutionResult:
    """Durable outcome of evaluating one staged source version."""

    run_id: str
    source_record_id: str
    outcome: str
    candidates: Tuple[CandidateMatch, ...]
    review_id: Optional[str]
    replayed: bool


@dataclass(frozen=True)
class ApprovalResult:
    """Result of a human approval and P1.2 crosswalk activation."""

    review_id: str
    candidate_evidence_id: str
    crosswalk_id: str
    replayed: bool


def candidate_tuple(values: Sequence[CandidateMatch]) -> Tuple[CandidateMatch, ...]:
    """Return candidates as an immutable tuple for public results."""
    return tuple(values)
