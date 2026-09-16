"""
Global FastAPI Exception Handlers mapping application service exceptions
to standard ErrorResponse payloads.
"""

import logging
from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import RecommendationValidationError
from app.schemas.error import ErrorResponse
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError

logger = logging.getLogger(__name__)


def _get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown-correlation-id")


async def resource_not_found_handler(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    error_payload = ErrorResponse(
        error_code="RESOURCE_NOT_FOUND",
        message=str(exc),
        details={},
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=error_payload.model_dump(),
    )


async def resource_inactive_handler(request: Request, exc: ResourceInactiveError) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    error_payload = ErrorResponse(
        error_code="RESOURCE_INACTIVE",
        message=str(exc),
        details={},
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload.model_dump(),
    )


async def recommendation_validation_handler(
    request: Request, exc: RecommendationValidationError
) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    error_payload = ErrorResponse(
        error_code="RECOMMENDATION_VALIDATION_FAILED",
        message=str(exc),
        details={},
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_payload.model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    details: dict[str, Any] = {"errors": exc.errors()}
    error_payload = ErrorResponse(
        error_code="INVALID_REQUEST_BODY",
        message="Invalid request body payload",
        details=details,
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=error_payload.model_dump(),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    msg = exc.detail if isinstance(exc.detail, str) else "HTTP exception occurred"
    details = exc.detail if isinstance(exc.detail, dict) else {}
    error_payload = ErrorResponse(
        error_code=f"HTTP_{exc.status_code}",
        message=msg,
        details=details,
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload.model_dump(),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = _get_correlation_id(request)
    logger.exception("Unhandled server error", extra={"correlation_id": correlation_id})
    error_payload = ErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred",
        details={},
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_payload.model_dump(),
    )
