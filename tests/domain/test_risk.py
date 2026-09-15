from datetime import date

import pytest

from app.domain.enums import RiskSeverity
from app.domain.exceptions import (
    InvalidInventoryError,
    InvalidSafetyStockError,
    ZeroDemandError,
)
from app.domain.risk import (
    calculate_days_to_stockout,
    calculate_projected_stockout_date,
    calculate_safety_stock_units,
    calculate_shortage_quantity,
    classify_risk_severity,
    evaluate_stockout_risk,
)


def test_calculate_days_to_stockout_normal() -> None:
    assert calculate_days_to_stockout(100, 40.0) == 2.5


def test_calculate_days_to_stockout_zero_demand_raises_error() -> None:
    with pytest.raises(ZeroDemandError):
        calculate_days_to_stockout(100, 0.0)


def test_calculate_days_to_stockout_negative_inventory_raises_error() -> None:
    with pytest.raises(InvalidInventoryError):
        calculate_days_to_stockout(-10, 40.0)


def test_calculate_safety_stock_units() -> None:
    assert calculate_safety_stock_units(7, 40.0) == 280.0


def test_calculate_safety_stock_invalid_days_raises_error() -> None:
    with pytest.raises(InvalidSafetyStockError):
        calculate_safety_stock_units(0, 40.0)


def test_calculate_shortage_quantity() -> None:
    assert calculate_shortage_quantity(280.0, 100) == 180
    assert calculate_shortage_quantity(280.0, 300) == 0


def test_classify_risk_severity_thresholds() -> None:
    assert classify_risk_severity(2.9) == RiskSeverity.CRITICAL
    assert classify_risk_severity(3.0) == RiskSeverity.HIGH
    assert classify_risk_severity(6.9) == RiskSeverity.HIGH
    assert classify_risk_severity(7.0) == RiskSeverity.MEDIUM
    assert classify_risk_severity(14.0) == RiskSeverity.MEDIUM
    assert classify_risk_severity(14.1) == RiskSeverity.LOW


def test_calculate_projected_stockout_date() -> None:
    start_date = date(2026, 9, 16)
    # floor(2.5) = 2 days
    assert calculate_projected_stockout_date(start_date, 2.5) == date(2026, 9, 18)


def test_evaluate_stockout_risk_integration() -> None:
    assessment = evaluate_stockout_risk(
        available_inventory=100,
        average_daily_demand=40.0,
        safety_stock_days=7,
        detection_date=date(2026, 9, 16),
    )
    assert assessment.available_inventory == 100
    assert assessment.average_daily_demand == 40.0
    assert assessment.days_to_stockout == 2.5
    assert assessment.target_safety_stock_units == 280.0
    assert assessment.shortage_quantity == 180
    assert assessment.severity == RiskSeverity.CRITICAL
    assert assessment.projected_stockout_date == date(2026, 9, 18)
