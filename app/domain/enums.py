from enum import StrEnum


class RiskSeverity(StrEnum):
    """Stockout risk severity levels based on Days to Stockout (DUS)."""

    CRITICAL = "CRITICAL"  # DUS < 3 days
    HIGH = "HIGH"          # 3 <= DUS < 7 days
    MEDIUM = "MEDIUM"      # 7 <= DUS <= 14 days
    LOW = "LOW"            # DUS > 14 days


class IncidentStatus(StrEnum):
    """Lifecycle states for a stockout RiskIncident."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class RecommendationStatus(StrEnum):
    """Lifecycle states for a TransferRecommendation."""

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RecommendationSource(StrEnum):
    """Source provenance tag for a TransferRecommendation."""

    AI = "AI"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class PlannerAction(StrEnum):
    """Action types logged in append-only AuditEvent records."""

    RISK_DETECTED = "RISK_DETECTED"
    RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    NO_FEASIBLE_SOURCE_FOUND = "NO_FEASIBLE_SOURCE_FOUND"
    PLANNER_APPROVED = "PLANNER_APPROVED"
    PLANNER_REJECTED = "PLANNER_REJECTED"

