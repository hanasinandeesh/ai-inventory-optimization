class DomainError(Exception):
    """Base exception for all domain layer business validation failures."""

    pass


class InvalidInventoryError(DomainError):
    """Raised when inventory quantities violate domain invariants (e.g. negative values)."""

    pass


class InvalidDemandError(DomainError):
    """Raised when daily demand signals violate domain requirements (e.g. non-14 day series)."""

    pass


class ZeroDemandError(DomainError):
    """Raised when average daily demand rate is zero or invalid for division."""

    pass


class InvalidSafetyStockError(DomainError):
    """Raised when safety stock parameters violate domain invariants."""

    pass


class InvalidTransferError(DomainError):
    """Raised when transfer quantity or route cost parameters are invalid."""

    pass


class InfeasibleTransferError(DomainError):
    """Raised when a candidate transfer fails deterministic feasibility checks."""

    pass


class RecommendationValidationError(DomainError):
    """Raised when a transfer recommendation fails deterministic post-validation guardrails."""

    pass
