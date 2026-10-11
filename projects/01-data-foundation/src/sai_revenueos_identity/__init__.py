"""SAI RevenueOS P1.2 canonical identity reference implementation."""

from .errors import *  # noqa: F401,F403
from .ids import PREFIX_REGISTRY, PrefixedIDGenerator, uuid7, validate_prefixed_id
from .normalization import SourceIdentity, normalize_source_identity
from .store import (
    CANONICAL_TARGET_TYPES,
    IDENTITY_STEWARD,
    IDENTITY_WRITER,
    RESOLUTION_WRITER,
    SOURCE_WRITER,
    IdentityStore,
)

__all__ = [
    "IdentityStore", "PrefixedIDGenerator", "uuid7", "validate_prefixed_id",
    "normalize_source_identity", "SourceIdentity", "PREFIX_REGISTRY",
    "CANONICAL_TARGET_TYPES", "IDENTITY_WRITER", "SOURCE_WRITER",
    "RESOLUTION_WRITER", "IDENTITY_STEWARD",
]
