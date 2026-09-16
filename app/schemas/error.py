"""
Standardized API Error Response Schema.
Follows approved Phase 4 error response contract.
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized error payload returned by all API endpoints."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional context or validation details"
    )
    correlation_id: str = Field(..., description="Unique request correlation ID for tracing")
