"""
Application Service exceptions for application use-case orchestration errors.
"""


class ApplicationServiceError(Exception):
    """Base exception for all application service layer failures."""

    pass


class ResourceNotFoundError(ApplicationServiceError):
    """Raised when a requested resource (DC, Product, Inventory, Policy) is not found."""

    pass


class ResourceInactiveError(ApplicationServiceError):
    """Raised when a target resource (DC, Route) is in an inactive state."""

    pass


class InvalidStateTransitionError(ApplicationServiceError):
    """Raised when a state transition cannot be performed due to current state constraints."""

    pass
