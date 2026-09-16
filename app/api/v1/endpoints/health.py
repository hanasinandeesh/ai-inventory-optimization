from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import check_db_connection, get_db
from app.schemas.health import HealthCheckResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Health Check Endpoint",
    description="Verifies operational status of application and database connectivity.",
)
def get_health(
    db: Annotated[Session, Depends(get_db)],
) -> HealthCheckResponse | JSONResponse:
    try:
        check_db_connection(db)
        db_status = "connected"
    except SQLAlchemyError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": {
                    "status": "error",
                    "version": settings.VERSION,
                    "environment": settings.ENVIRONMENT,
                    "database": "disconnected",
                }
            },
        )

    return HealthCheckResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database=db_status,
    )
