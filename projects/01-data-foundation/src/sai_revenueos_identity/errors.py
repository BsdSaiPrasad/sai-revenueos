"""Domain errors for the P1.2 identity reference implementation."""


class IdentityError(Exception):
    """Base class for identity-domain errors."""


class ValidationError(IdentityError):
    """Input is malformed or violates an identity invariant."""


class AuthorizationError(IdentityError):
    """The caller lacks the required P1 write authority."""


class InvalidTransitionError(IdentityError):
    """A lifecycle transition is not allowed."""


class ConflictError(IdentityError):
    """The requested operation conflicts with current authoritative state."""


class IdempotencyConflictError(ConflictError):
    """An idempotency key was reused with a different request."""


class NotFoundError(IdentityError):
    """A referenced identity record does not exist."""


class SimulatedFailure(IdentityError):
    """Test-only failure used to prove transactional rollback."""
