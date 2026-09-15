"""
Domain layer package.

Contains pure, deterministic business logic, entities, calculations, and rules.
This package MUST NOT depend on FastAPI, SQLAlchemy, Pydantic DTO schemas, or external AI providers.
"""

from app.domain.demand import calculate_average_daily_demand
from app.domain.enums import (
    IncidentStatus,
    PlannerAction,
    RecommendationSource,
    RecommendationStatus,
    RiskSeverity,
)
from app.domain.exceptions import (
    DomainError,
    InfeasibleTransferError,
    InvalidDemandError,
    InvalidInventoryError,
    InvalidSafetyStockError,
    InvalidTransferError,
    RecommendationValidationError,
    ZeroDemandError,
)
from app.domain.inventory import InventoryBalance, calculate_available_inventory
from app.domain.recommendation import (
    RecommendationProposal,
    select_fallback_candidate,
    validate_recommendation_proposal,
)
from app.domain.risk import (
    RiskAssessmentResult,
    calculate_days_to_stockout,
    calculate_projected_stockout_date,
    calculate_safety_stock_units,
    calculate_shortage_quantity,
    classify_risk_severity,
    evaluate_stockout_risk,
)
from app.domain.transfer import (
    PreValidatedCandidate,
    calculate_estimated_transfer_cost,
    calculate_feasible_transfer_quantity,
    calculate_source_surplus,
    is_candidate_feasible,
)

__all__ = [
    "RiskSeverity",
    "IncidentStatus",
    "RecommendationStatus",
    "RecommendationSource",
    "PlannerAction",
    "DomainError",
    "InvalidInventoryError",
    "InvalidDemandError",
    "ZeroDemandError",
    "InvalidSafetyStockError",
    "InvalidTransferError",
    "InfeasibleTransferError",
    "RecommendationValidationError",
    "InventoryBalance",
    "calculate_available_inventory",
    "calculate_average_daily_demand",
    "RiskAssessmentResult",
    "calculate_days_to_stockout",
    "calculate_safety_stock_units",
    "calculate_shortage_quantity",
    "classify_risk_severity",
    "calculate_projected_stockout_date",
    "evaluate_stockout_risk",
    "PreValidatedCandidate",
    "calculate_source_surplus",
    "calculate_feasible_transfer_quantity",
    "is_candidate_feasible",
    "calculate_estimated_transfer_cost",
    "RecommendationProposal",
    "select_fallback_candidate",
    "validate_recommendation_proposal",
]
