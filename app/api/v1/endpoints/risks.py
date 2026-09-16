"""
API endpoints for querying stockout risk incidents.
GET /api/v1/risks
GET /api/v1/risks/{incident_id}
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_recommendation_service, get_risk_query_service
from app.schemas.error import ErrorResponse
from app.schemas.recommendation import RecommendationResponse
from app.schemas.risk import RiskIncidentResponse
from app.services.recommendation_service import RecommendationService
from app.services.risk_query_service import RiskQueryService

router = APIRouter()


@router.get(
    "",
    response_model=list[RiskIncidentResponse],
    status_code=status.HTTP_200_OK,
    summary="List risk incidents",
    description="Retrieves all persisted stockout risk incidents ordered newest first.",
    responses={
        200: {
            "model": list[RiskIncidentResponse],
            "description": "List of persisted risk incidents retrieved successfully",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def list_risks(
    service: Annotated[RiskQueryService, Depends(get_risk_query_service)],
) -> list[RiskIncidentResponse]:
    incidents = service.list_risks()
    return [
        RiskIncidentResponse(
            id=item.id,
            incident_code=item.incident_code,
            target_dc_code=item.target_dc_code,
            sku=item.sku,
            current_dos=item.current_dos,
            days_to_stockout=item.days_to_stockout,
            projected_stockout_date=item.projected_stockout_date,
            shortage_qty=item.shortage_qty,
            severity=item.severity,
            status=item.status,
            detected_at=item.detected_at,
        )
        for item in incidents
    ]


@router.get(
    "/{incident_id}",
    response_model=RiskIncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single risk incident by ID",
    description="Retrieves a single stockout risk incident by its database ID.",
    responses={
        200: {
            "model": RiskIncidentResponse,
            "description": "Risk incident retrieved successfully",
        },
        404: {
            "model": ErrorResponse,
            "description": "Risk incident not found",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def get_risk(
    incident_id: int,
    service: Annotated[RiskQueryService, Depends(get_risk_query_service)],
) -> RiskIncidentResponse:
    item = service.get_risk(incident_id)
    return RiskIncidentResponse(
        id=item.id,
        incident_code=item.incident_code,
        target_dc_code=item.target_dc_code,
        sku=item.sku,
        current_dos=item.current_dos,
        days_to_stockout=item.days_to_stockout,
        projected_stockout_date=item.projected_stockout_date,
        shortage_qty=item.shortage_qty,
        severity=item.severity,
        status=item.status,
        detected_at=item.detected_at,
    )


@router.post(
    "/{incident_id}/recommendations",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger transfer recommendation generation",
    description=(
        "Generates an AI-driven or deterministic fallback inventory transfer recommendation "
        "for an OPEN RiskIncident."
    ),
    responses={
        200: {
            "model": RecommendationResponse,
            "description": "Recommendation generated or processed successfully",
        },
        404: {
            "model": ErrorResponse,
            "description": "Risk incident not found",
        },
        422: {
            "model": ErrorResponse,
            "description": "Incident is not OPEN or recommendation validation failed",
        },
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def trigger_recommendation(
    incident_id: int,
    service: Annotated[RecommendationService, Depends(get_recommendation_service)],
) -> RecommendationResponse:
    result = service.generate_recommendation(incident_id)

    return RecommendationResponse(
        has_recommendation=result.has_recommendation,
        status=result.status,
        recommendation_id=result.recommendation_id,
        recommendation_code=result.recommendation_code,
        incident_id=result.incident_id,
        source_dc_code=result.source_dc_code,
        target_dc_code=result.target_dc_code,
        product_sku=result.product_sku,
        recommended_qty=result.recommended_qty,
        estimated_total_cost=float(result.estimated_total_cost)
        if result.estimated_total_cost is not None
        else None,
        recommendation_source=result.recommendation_source,
        rationale=result.rationale,
        created_at=result.created_at,
    )
