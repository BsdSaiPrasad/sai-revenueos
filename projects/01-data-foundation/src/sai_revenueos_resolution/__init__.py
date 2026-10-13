"""P1.8 deterministic identity resolution, survivorship, and manual review."""

from .errors import (
    ResolutionAuthorizationError,
    ResolutionConflictError,
    ResolutionError,
    ResolutionValidationError,
    SimulatedResolutionFailure,
    StaleReviewError,
)
from .matcher import DeterministicMatcher
from .models import ApprovalResult, CandidateMatch, ResolutionResult, StagedIdentityRecord
from .policy import EntityMatchPolicy, ResolutionPolicy
from .service import ResolutionService
from .staging import MemoryStagingReader, SnowflakeStagingReader, record_from_source_event
from .store import ResolutionStore

__all__ = [
    "ApprovalResult", "CandidateMatch", "DeterministicMatcher", "EntityMatchPolicy",
    "MemoryStagingReader", "ResolutionAuthorizationError", "ResolutionConflictError",
    "ResolutionError", "ResolutionPolicy", "ResolutionResult", "ResolutionService",
    "ResolutionStore", "ResolutionValidationError", "SimulatedResolutionFailure",
    "SnowflakeStagingReader", "StagedIdentityRecord", "StaleReviewError",
    "record_from_source_event",
]
