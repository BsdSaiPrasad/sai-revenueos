"""Standards-compliant UUIDv7 and controlled SAI RevenueOS identifiers."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Callable, Dict, Optional

from .errors import ConflictError, ValidationError


# This registry is the only approved mapping from entity type to public ID prefix.
# The canonical contract contains 23 business structures; the final entries support
# the P1.2 operational reference layer without adding new canonical business entities.
PREFIX_REGISTRY: Dict[str, str] = {
    "Account": "sai_acc_",
    "Person": "sai_person_",
    "AccountPersonRelationship": "sai_accperson_",
    "Opportunity": "sai_opp_",
    "OpportunityPersonRole": "sai_oppperson_",
    "Activity": "sai_act_",
    "Campaign": "sai_campaign_",
    "Quote": "sai_quote_",
    "Contract": "sai_contract_",
    "Order": "sai_order_",
    "Subscription": "sai_sub_",
    "Invoice": "sai_inv_",
    "ProductUser": "sai_puser_",
    "SupportCase": "sai_case_",
    "Signal": "sai_signal_",
    "EnrichmentSnapshot": "sai_enrich_",
    "Decision": "sai_decision_",
    "WorkflowRun": "sai_run_",
    "ExternalIdentityCrosswalk": "sai_xwalk_",
    "SourceRecord": "sai_src_",
    "AccountHierarchyRelationship": "sai_acchier_",
    "AccountNameHistory": "sai_accname_",
    "AccountDomainHistory": "sai_accdomain_",
    "ResolutionCase": "sai_rescase_",
    "CandidateEvidence": "sai_candidate_",
    "IdentityMergeEvent": "sai_merge_",
    "AuditEvent": "sai_audit_",
    "SourceObservation": "sai_observation_",
}


def uuid7(
    timestamp_ms: Optional[int] = None,
    random_bits: Optional[int] = None,
) -> uuid.UUID:
    """Return a UUIDv7 value using the RFC 9562 bit layout.

    The function is local so the reference implementation works on Python versions
    that predate ``uuid.uuid7``. Callers may inject time and randomness in tests.
    """

    if timestamp_ms is None:
        timestamp_ms = time.time_ns() // 1_000_000
    if not 0 <= timestamp_ms < (1 << 48):
        raise ValidationError("UUIDv7 timestamp must fit in 48 bits")

    if random_bits is None:
        random_bits = secrets.randbits(74)
    if not 0 <= random_bits < (1 << 74):
        raise ValidationError("UUIDv7 random payload must fit in 74 bits")

    rand_a = random_bits >> 62
    rand_b = random_bits & ((1 << 62) - 1)
    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0x2 << 62  # RFC 4122 / RFC 9562 variant bits: binary 10.
    value |= rand_b
    return uuid.UUID(int=value)


class PrefixedIDGenerator:
    """Generate entity-prefixed UUIDv7 IDs with collision detection and retry."""

    def __init__(
        self,
        max_attempts: int = 5,
        uuid_factory: Optional[Callable[[], uuid.UUID]] = None,
    ) -> None:
        if max_attempts < 1:
            raise ValidationError("max_attempts must be positive")
        self._max_attempts = max_attempts
        self._uuid_factory = uuid_factory or uuid7
        self._clock_lock = threading.Lock()
        self._last_timestamp_ms = -1

    def _next_uuid(self) -> uuid.UUID:
        if self._uuid_factory is not uuid7:
            value = self._uuid_factory()
            if value.version != 7:
                raise ValidationError("UUID factory must return UUIDv7 values")
            return value

        # Prevent local clock rollback from making newly generated values older than
        # values created by this generator instance. Random bits still provide the
        # within-millisecond uniqueness component required by UUIDv7.
        with self._clock_lock:
            now_ms = time.time_ns() // 1_000_000
            effective_ms = max(now_ms, self._last_timestamp_ms)
            self._last_timestamp_ms = effective_ms
            return uuid7(timestamp_ms=effective_ms)

    def generate(
        self,
        entity_type: str,
        exists: Optional[Callable[[str], bool]] = None,
    ) -> str:
        prefix = PREFIX_REGISTRY.get(entity_type)
        if prefix is None:
            raise ValidationError("unregistered entity type: %s" % entity_type)
        collision_check = exists or (lambda _: False)
        for _ in range(self._max_attempts):
            candidate = prefix + str(self._next_uuid())
            if not collision_check(candidate):
                return candidate
        raise ConflictError("could not allocate a unique ID after safe retries")


def validate_prefixed_id(entity_type: str, value: str) -> None:
    """Validate the registered prefix, UUID syntax, version, and variant."""

    prefix = PREFIX_REGISTRY.get(entity_type)
    if prefix is None:
        raise ValidationError("unregistered entity type: %s" % entity_type)
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValidationError("ID does not use the registered %s prefix" % entity_type)
    try:
        parsed = uuid.UUID(value[len(prefix) :])
    except (ValueError, AttributeError) as exc:
        raise ValidationError("ID payload is not a UUID") from exc
    if parsed.version != 7 or parsed.variant != uuid.RFC_4122:
        raise ValidationError("ID payload must be an RFC 9562 UUIDv7")
