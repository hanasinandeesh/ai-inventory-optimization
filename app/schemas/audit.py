"""
Pydantic schemas for audit API contracts.
Must NOT depend on ORM database models or infrastructure.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventResponse(BaseModel):
    """Response payload representing an audit event entry."""

    id: int = Field(..., description="Surrogate database ID of audit event")
    incident_id: int = Field(..., description="Associated RiskIncident ID")
    action: str = Field(..., description="Audit action type")
    recommendation_id: int | None = Field(
        default=None, description="Associated recommendation ID if applicable"
    )
    planner_id: str | None = Field(
        default=None, description="Planner ID who performed action or None if system-generated"
    )
    input_snapshot_json: str | None = Field(
        default=None, description="JSON snapshot data associated with event"
    )
    final_approved_qty: int | None = Field(
        default=None, description="Final approved quantity if planner approved"
    )
    created_at: datetime = Field(..., description="Timestamp when event was created")
