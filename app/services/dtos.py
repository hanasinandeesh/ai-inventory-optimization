"""
Application Data Transfer Objects (DTOs) for Application Services.
Must NOT depend on FastAPI, Pydantic, or SQLAlchemy ORM models.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.transfer import PreValidatedCandidate


@dataclass(frozen=True)
class DistributionCenterDTO:
    """Application DTO for Distribution Center entity data."""

    id: int
    code: str
    name: str
    city: str
    state: str
    is_active: bool


@dataclass(frozen=True)
class ProductDTO:
    """Application DTO for Product entity data."""

    id: int
    sku: str
    name: str
    category: str
    unit_of_measure: str
    pack_size: int = 1


@dataclass(frozen=True)
class InventoryBalanceDTO:
    """Application DTO for Inventory Balance entity data."""

    id: int
    dc_id: int
    product_id: int
    on_hand_qty: int
    reserved_qty: int


@dataclass(frozen=True)
class DailyDemandSignalDTO:
    """Application DTO for Daily Demand Signal data."""

    id: int
    dc_id: int
    product_id: int
    signal_date: date
    daily_demand_qty: int


@dataclass(frozen=True)
class InventoryPolicyDTO:
    """Application DTO for Inventory Policy data."""

    id: int
    dc_id: int
    product_id: int
    safety_stock_days: float
    min_reorder_qty: int = 0
    is_active: bool = True


@dataclass(frozen=True)
class RiskIncidentDTO:
    """Application DTO for Risk Incident entity data."""

    id: int
    incident_code: str
    target_dc_id: int
    product_id: int
    current_dos: float
    days_to_stockout: float
    projected_stockout_date: date
    shortage_qty: float
    severity: str
    status: str
    detected_at: datetime | None = None


@dataclass(frozen=True)
class RiskIncidentDetailDTO:
    """Application DTO representing a fully resolved Risk Incident with DC code and SKU."""

    id: int
    incident_code: str
    target_dc_id: int
    target_dc_code: str
    product_id: int
    sku: str
    current_dos: float
    days_to_stockout: float
    projected_stockout_date: date
    shortage_qty: float
    severity: str
    status: str
    detected_at: datetime


@dataclass(frozen=True)
class RiskIncidentCreateData:
    """Input DTO for creating a new Risk Incident."""

    incident_code: str
    target_dc_id: int
    product_id: int
    current_dos: float
    days_to_stockout: float
    projected_stockout_date: date
    shortage_qty: float
    severity: str
    status: str = "OPEN"
    detected_at: datetime | None = None


@dataclass(frozen=True)
class RiskIncidentUpdateData:
    """Input DTO for updating an existing Risk Incident."""

    incident_id: int
    current_dos: float
    days_to_stockout: float
    projected_stockout_date: date
    shortage_qty: float
    severity: str


@dataclass(frozen=True)
class AuditEventDTO:
    """Application DTO for Audit Event data."""

    id: int
    incident_id: int
    action: str
    recommendation_id: int | None = None
    planner_id: str | None = None
    input_snapshot_json: str | None = None
    final_approved_qty: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class AuditEventCreateData:
    """Input DTO for creating an Audit Event."""

    incident_id: int
    action: str
    recommendation_id: int | None = None
    planner_id: str | None = None
    input_snapshot_json: str | None = None
    final_approved_qty: int | None = None


@dataclass(frozen=True)
class DCRouteDTO:
    """Application DTO for DC Route entity data."""

    id: int
    source_dc_id: int
    target_dc_id: int
    transit_days: int
    cost_per_unit: float
    is_active: bool
    distance_miles: float | None = None


@dataclass(frozen=True)
class ProcessRiskDetectionResult:
    """Dataclass representing the result of ProcessRiskDetectionService."""

    incident_id: int
    incident_code: str
    target_dc_id: int
    target_dc_code: str
    product_id: int
    product_sku: str
    available_inventory: int
    average_daily_demand: float
    days_to_stockout: float
    projected_stockout_date: date
    target_safety_stock_units: float
    shortage_quantity: int
    severity: str
    status: str
    is_new_incident: bool
    detected_at: datetime


@dataclass(frozen=True)
class CandidateDiscoveryResultDTO:
    """Dataclass representing the output of CandidateDiscoveryService."""

    incident_id: int
    incident_code: str
    target_dc_id: int
    target_dc_code: str
    product_id: int
    target_shortage_qty: int
    days_to_stockout: float
    feasible_candidates: list[PreValidatedCandidate]


@dataclass(frozen=True)
class AIRecommendationInputDTO:
    """Pure DTO containing business context for AI recommendation ranking."""

    incident_code: str
    target_dc_code: str
    product_sku: str
    product_name: str
    category: str
    days_to_stockout: float
    shortage_qty: int
    severity: str
    prevalidated_candidates: list[PreValidatedCandidate]


@dataclass(frozen=True)
class AIRecommendationOutputDTO:
    """Pure DTO representing the response from an AI provider."""

    selected_candidate_id: str
    rationale: str


@dataclass(frozen=True)
class TransferRecommendationCreateData:
    """Input dataclass for creating a TransferRecommendation record."""

    recommendation_code: str
    incident_id: int
    source_dc_id: int
    target_dc_id: int
    product_id: int
    recommended_qty: int
    feasible_qty_snapshot: int
    source_surplus_snapshot: int
    transit_days_snapshot: int
    route_unit_cost_snapshot: Decimal
    estimated_cost_snapshot: Decimal
    rationale: str
    recommendation_source: str
    status: str = "PROPOSED"


@dataclass(frozen=True)
class TransferRecommendationDTO:
    """Application DTO representing a persisted TransferRecommendation entity."""

    id: int
    recommendation_code: str
    incident_id: int
    source_dc_id: int
    target_dc_id: int
    product_id: int
    recommended_qty: int
    feasible_qty_snapshot: int
    source_surplus_snapshot: int
    transit_days_snapshot: int
    route_unit_cost_snapshot: Decimal
    estimated_cost_snapshot: Decimal
    rationale: str
    recommendation_source: str
    status: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class RecommendationResultDTO:
    """Dataclass representing the outcome of RecommendationService execution."""

    has_recommendation: bool
    status: str
    recommendation_id: int | None = None
    recommendation_code: str | None = None
    incident_id: int | None = None
    source_dc_id: int | None = None
    source_dc_code: str | None = None
    target_dc_id: int | None = None
    target_dc_code: str | None = None
    product_id: int | None = None
    product_sku: str | None = None
    recommended_qty: int | None = None
    estimated_total_cost: Decimal | None = None
    recommendation_source: str | None = None
    rationale: str | None = None
    created_at: datetime | None = None
