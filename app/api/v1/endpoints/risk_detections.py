"""
API endpoint for triggering stockout risk detection.
POST /api/v1/risk-detections
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_process_risk_detection_service
from app.schemas.error import ErrorResponse
from app.schemas.risk import RiskIncidentResponse, TriggerRiskDetectionRequest
from app.services.process_risk_detection_service import ProcessRiskDetectionService

router = APIRouter()


@router.post(
    "",
    response_model=RiskIncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger inventory risk detection",
    description=(
        "Evaluates stockout risk for a target Distribution Center and SKU. "
        "Creates or updates an OPEN RiskIncident."
    ),
    responses={
        200: {
            "model": RiskIncidentResponse,
            "description": "Risk detection successfully triggered",
        },
        400: {"model": ErrorResponse, "description": "Invalid request body payload"},
        404: {
            "model": ErrorResponse,
            "description": "Target Distribution Center or SKU not found",
        },
        422: {
            "model": ErrorResponse,
            "description": "Target Distribution Center is inactive",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def trigger_risk_detection(
    request: TriggerRiskDetectionRequest,
    service: Annotated[ProcessRiskDetectionService, Depends(get_process_risk_detection_service)],
) -> RiskIncidentResponse:
    detection_date = request.detection_date or datetime.now(UTC).date()

    result = service.process_risk_detection(
        target_dc_id_or_code=request.dc_code,
        product_id_or_sku=request.sku,
        detection_date=detection_date,
    )

    return RiskIncidentResponse(
        id=result.incident_id,
        incident_code=result.incident_code,
        target_dc_code=result.target_dc_code,
        sku=result.product_sku,
        current_dos=result.days_to_stockout,
        days_to_stockout=result.days_to_stockout,
        projected_stockout_date=result.projected_stockout_date,
        shortage_qty=float(result.shortage_quantity),
        severity=result.severity,
        status=result.status,
        detected_at=result.detected_at,
    )
