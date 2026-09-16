"""
API endpoints for planner transfer recommendation decisions (Approval & Rejection).
POST /api/v1/recommendations/{recommendation_id}/approve
POST /api/v1/recommendations/{recommendation_id}/reject
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_planner_decision_service
from app.schemas.decision import (
    ApproveRecommendationRequest,
    PlannerDecisionResponse,
    RejectRecommendationRequest,
)
from app.schemas.error import ErrorResponse
from app.services.planner_decision_service import PlannerDecisionService

router = APIRouter()


@router.post(
    "/{recommendation_id}/approve",
    response_model=PlannerDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve transfer recommendation",
    description="Approves a proposed or validated inventory transfer recommendation.",
    responses={
        200: {
            "model": PlannerDecisionResponse,
            "description": "Recommendation approved successfully",
        },
        404: {
            "model": ErrorResponse,
            "description": "Recommendation or associated incident not found",
        },
        409: {
            "model": ErrorResponse,
            "description": "State transition conflict (recommendation already decided)",
        },
        400: {"model": ErrorResponse, "description": "Invalid request payload"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def approve_recommendation(
    recommendation_id: int,
    payload: ApproveRecommendationRequest,
    service: Annotated[PlannerDecisionService, Depends(get_planner_decision_service)],
) -> PlannerDecisionResponse:
    result = service.approve_recommendation(
        recommendation_id=recommendation_id,
        planner_id=payload.planner_id,
        comment=payload.comment,
    )
    return PlannerDecisionResponse(
        recommendation_id=result.recommendation_id,
        recommendation_code=result.recommendation_code,
        status=result.status,
        incident_id=result.incident_id,
        incident_status=result.incident_status,
        planner_id=result.planner_id,
        comment=result.comment,
        rejection_reason=result.rejection_reason,
        recommended_qty=result.recommended_qty,
        estimated_total_cost=float(result.estimated_total_cost),
        decided_at=result.decided_at,
    )


@router.post(
    "/{recommendation_id}/reject",
    response_model=PlannerDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject transfer recommendation",
    description="Rejects a proposed or validated inventory transfer recommendation.",
    responses={
        200: {
            "model": PlannerDecisionResponse,
            "description": "Recommendation rejected successfully",
        },
        404: {
            "model": ErrorResponse,
            "description": "Recommendation or associated incident not found",
        },
        409: {
            "model": ErrorResponse,
            "description": "State transition conflict (recommendation already decided)",
        },
        400: {"model": ErrorResponse, "description": "Invalid request payload"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
def reject_recommendation(
    recommendation_id: int,
    payload: RejectRecommendationRequest,
    service: Annotated[PlannerDecisionService, Depends(get_planner_decision_service)],
) -> PlannerDecisionResponse:
    result = service.reject_recommendation(
        recommendation_id=recommendation_id,
        planner_id=payload.planner_id,
        rejection_reason=payload.rejection_reason,
    )
    return PlannerDecisionResponse(
        recommendation_id=result.recommendation_id,
        recommendation_code=result.recommendation_code,
        status=result.status,
        incident_id=result.incident_id,
        incident_status=result.incident_status,
        planner_id=result.planner_id,
        comment=result.comment,
        rejection_reason=result.rejection_reason,
        recommended_qty=result.recommended_qty,
        estimated_total_cost=float(result.estimated_total_cost),
        decided_at=result.decided_at,
    )
