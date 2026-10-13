"""Errors raised by the P1.8 identity-resolution reference layer."""


class ResolutionError(Exception):
    """Base error for deterministic matching and review orchestration."""


class ResolutionValidationError(ResolutionError):
    """Raised when staged input or a policy is invalid."""


class ResolutionConflictError(ResolutionError):
    """Raised when a retry conflicts with already stored resolution evidence."""


class StaleReviewError(ResolutionConflictError):
    """Raised when a decision targets an older P1.2 resolution-case version."""


class ResolutionAuthorizationError(ResolutionError):
    """Raised when a caller lacks identity-steward authority."""


class SimulatedResolutionFailure(ResolutionError):
    """Test-only failure used to prove idempotent review recovery."""
