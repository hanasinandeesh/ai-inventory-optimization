"""API v1 router composition."""

from fastapi import APIRouter

from app.api.v1.endpoints import health, risk_detections

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(
    risk_detections.router, prefix="/risk-detections", tags=["Risk Detections"]
)
