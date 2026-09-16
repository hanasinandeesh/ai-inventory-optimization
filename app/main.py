from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.exception_handlers import (
    http_exception_handler,
    recommendation_validation_handler,
    resource_inactive_handler,
    resource_not_found_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.v1.api import api_router
from app.api.v1.endpoints import health
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.core.middleware import CorrelationIdMiddleware
from app.domain.exceptions import RecommendationValidationError
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown event handler."""
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]...")
    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")


def create_application() -> FastAPI:
    """Factory creating FastAPI application instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # Set up Correlation ID middleware
    app.add_middleware(CorrelationIdMiddleware)

    # Set up CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    app.add_exception_handler(ResourceNotFoundError, resource_not_found_handler)
    app.add_exception_handler(ResourceInactiveError, resource_inactive_handler)
    app.add_exception_handler(RecommendationValidationError, recommendation_validation_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Mount API routes
    app.include_router(api_router, prefix=settings.API_V1_STR)
    # Also mount health router directly at root /health for infrastructure probes
    app.include_router(health.router)

    return app


app = create_application()
