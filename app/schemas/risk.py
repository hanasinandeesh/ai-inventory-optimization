"""
Pydantic schemas for risk detection API request and response contracts.
Must NOT depend on ORM database models or infrastructure.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class TriggerRiskDetectionRequest(BaseModel):
    """Request payload for triggering inventory stockout risk detection."""

    dc_code: str = Field(
        ...,
        min_length=1,
        description="Target Distribution Center business code",
        examples=["DC-CHI"],
    )
    sku: str = Field(
        ...,
        min_length=1,
        description="Product SKU business identifier",
        examples=["SKU-8842"],
    )
    detection_date: date | None = Field(
        default=None,
        description="Optional risk detection reference date.",
    )


class RiskIncidentResponse(BaseModel):
    """Response payload representing detected stockout risk incident."""

    id: int = Field(..., description="Unique database surrogate identifier of RiskIncident")
    incident_code: str = Field(..., description="Unique business incident code")
    target_dc_code: str = Field(..., description="Target Distribution Center code")
    sku: str = Field(..., description="Product SKU identifier")
    current_dos: float = Field(..., description="Current Days of Supply")
    days_to_stockout: float = Field(..., description="Estimated days until stockout")
    projected_stockout_date: date = Field(..., description="Projected stockout date")
    shortage_qty: float = Field(..., description="Projected inventory shortage quantity")
    severity: str = Field(..., description="Risk severity (CRITICAL, HIGH, MEDIUM, LOW)")
    status: str = Field(..., description="Incident status (OPEN, etc.)")
    detected_at: datetime = Field(..., description="Timestamp when incident was detected")
