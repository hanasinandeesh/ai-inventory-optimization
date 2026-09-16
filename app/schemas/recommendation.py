"""
Pydantic schemas for transfer recommendation API contracts.
Must NOT depend on ORM database models or infrastructure.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class RecommendationResponse(BaseModel):
    """Response payload representing the outcome of transfer recommendation generation."""

    has_recommendation: bool = Field(
        ..., description="Indicates if a valid transfer recommendation was generated"
    )
    status: str = Field(
        ..., description="Recommendation status (PROPOSED, NO_FEASIBLE_SOURCE_FOUND, etc.)"
    )
    recommendation_id: int | None = Field(
        default=None, description="Database surrogate ID of generated recommendation"
    )
    recommendation_code: str | None = Field(
        default=None, description="Unique business recommendation code"
    )
    incident_id: int | None = Field(default=None, description="Associated RiskIncident ID")
    source_dc_code: str | None = Field(
        default=None, description="Recommended source Distribution Center code"
    )
    target_dc_code: str | None = Field(default=None, description="Target Distribution Center code")
    product_sku: str | None = Field(default=None, description="Product SKU identifier")
    recommended_qty: int | None = Field(
        default=None, description="Recommended transfer quantity in units"
    )
    estimated_total_cost: float | None = Field(
        default=None, description="Estimated total cost for transfer shipment"
    )
    recommendation_source: str | None = Field(
        default=None, description="Source of recommendation (AI or DETERMINISTIC_FALLBACK)"
    )
    rationale: str | None = Field(
        default=None, description="Explanation or rationale for recommendation"
    )
    created_at: datetime | None = Field(
        default=None, description="Timestamp when recommendation was generated"
    )
