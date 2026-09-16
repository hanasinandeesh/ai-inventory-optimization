import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.enums import RiskSeverity
from app.domain.exceptions import (
    InvalidInventoryError,
    InvalidSafetyStockError,
    ZeroDemandError,
)

# Centralized Risk Severity Thresholds (in Days of Supply)
SEVERITY_CRITICAL_THRESHOLD_DAYS: float = 3.0
SEVERITY_HIGH_THRESHOLD_DAYS: float = 7.0
SEVERITY_MEDIUM_THRESHOLD_DAYS: float = 14.0


@dataclass(frozen=True)
class RiskAssessmentResult:
    """Immutable value object holding deterministic risk evaluation output."""

    available_inventory: int
    average_daily_demand: float
    days_to_stockout: float
    projected_stockout_date: date
    target_safety_stock_units: float
    shortage_quantity: int
    severity: RiskSeverity


def calculate_days_to_stockout(available_inventory: int, average_daily_demand: float) -> float:
    """
    Computes Days to Stockout (DUS).
    Formula: Available Inventory / Average Daily Demand Rate
    In V1, Current DOS and DUS are mathematically equivalent.
    """
    if available_inventory < 0:
        raise InvalidInventoryError(
            f"Available inventory cannot be negative (got {available_inventory})"
        )
    if average_daily_demand <= 0:
        raise ZeroDemandError(
            f"Average daily demand rate must be strictly positive (got {average_daily_demand})"
        )
    return available_inventory / average_daily_demand


def calculate_safety_stock_units(safety_stock_days: int, average_daily_demand: float) -> float:
    """
    Computes target safety stock requirement in units.
    Formula: safety_stock_days * average_daily_demand
    """
    if safety_stock_days <= 0:
        raise InvalidSafetyStockError(
            f"Safety stock target days must be strictly positive (got {safety_stock_days})"
        )
    if average_daily_demand <= 0:
        raise ZeroDemandError(
            f"Average daily demand rate must be strictly positive (got {average_daily_demand})"
        )
    return float(safety_stock_days * average_daily_demand)


def calculate_shortage_quantity(target_safety_stock_units: float, available_inventory: int) -> int:
    """
    Computes safety stock shortage in units.
    Formula: max(0, target_safety_stock_units - available_inventory)
    """
    diff = target_safety_stock_units - available_inventory
    return max(0, int(round(diff)))


def classify_risk_severity(days_to_stockout: float) -> RiskSeverity:
    """
    Classifies stockout risk severity based on Days to Stockout (DUS):
    - CRITICAL: DUS < 3.0 days
    - HIGH: 3.0 <= DUS < 7.0 days
    - MEDIUM: 7.0 <= DUS <= 14.0 days
    - LOW: DUS > 14.0 days
    """
    if days_to_stockout < SEVERITY_CRITICAL_THRESHOLD_DAYS:
        return RiskSeverity.CRITICAL
    elif days_to_stockout < SEVERITY_HIGH_THRESHOLD_DAYS:
        return RiskSeverity.HIGH
    elif days_to_stockout <= SEVERITY_MEDIUM_THRESHOLD_DAYS:
        return RiskSeverity.MEDIUM
    else:
        return RiskSeverity.LOW


def calculate_projected_stockout_date(detection_date: date, days_to_stockout: float) -> date:
    """
    Computes projected stockout date.
    Formula: detection_date + floor(days_to_stockout)
    """
    return detection_date + timedelta(days=math.floor(days_to_stockout))


def evaluate_stockout_risk(
    available_inventory: int,
    average_daily_demand: float,
    safety_stock_days: int,
    detection_date: date,
) -> RiskAssessmentResult:
    """Orchestrates deterministic stockout risk assessment for a SKU at a facility."""
    dus = calculate_days_to_stockout(available_inventory, average_daily_demand)
    projected_date = calculate_projected_stockout_date(detection_date, dus)
    target_safety_stock = calculate_safety_stock_units(safety_stock_days, average_daily_demand)
    shortage = calculate_shortage_quantity(target_safety_stock, available_inventory)
    severity = classify_risk_severity(dus)

    return RiskAssessmentResult(
        available_inventory=available_inventory,
        average_daily_demand=average_daily_demand,
        days_to_stockout=dus,
        projected_stockout_date=projected_date,
        target_safety_stock_units=target_safety_stock,
        shortage_quantity=shortage,
        severity=severity,
    )
