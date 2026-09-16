"""API v1 router composition."""

from fastapi import APIRouter

from app.api.v1.endpoints import health, risk_detections, risks

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(
    risk_detections.router, prefix="/risk-detections", tags=["Risk Detections"]
)
api_router.include_router(risks.router, prefix="/risks", tags=["Risks"])
