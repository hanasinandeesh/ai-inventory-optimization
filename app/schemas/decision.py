"""
Pydantic schemas for Planner Decision API contracts (Approval & Rejection).
Must NOT depend on ORM database models or infrastructure.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ApproveRecommendationRequest(BaseModel):
    """Payload for approving a transfer recommendation."""

    planner_id: str = Field(
        ..., description="Identifier of the planner approving the recommendation"
    )
    comment: str | None = Field(
        default=None, description="Optional comment or notes for approval decision"
    )


class RejectRecommendationRequest(BaseModel):
    """Payload for rejecting a transfer recommendation."""

    planner_id: str = Field(
        ..., description="Identifier of the planner rejecting the recommendation"
    )
    rejection_reason: str = Field(..., description="Reason or justification for rejection")


class PlannerDecisionResponse(BaseModel):
    """Response payload representing the outcome of a planner decision."""

    recommendation_id: int = Field(..., description="Surrogate database ID of recommendation")
    recommendation_code: str = Field(..., description="Unique recommendation code")
    status: str = Field(..., description="Updated recommendation status (APPROVED or REJECTED)")
    incident_id: int = Field(..., description="Associated RiskIncident ID")
    incident_status: str = Field(..., description="Updated incident status (RESOLVED or OPEN)")
    planner_id: str | None = Field(default=None, description="Planner ID who rendered the decision")
    comment: str | None = Field(default=None, description="Approval comment if approved")
    rejection_reason: str | None = Field(default=None, description="Rejection reason if rejected")
    recommended_qty: int = Field(..., description="Recommended transfer quantity in units")
    estimated_total_cost: float = Field(..., description="Estimated total cost for transfer")
    decided_at: datetime = Field(..., description="Timestamp when decision was persisted")
