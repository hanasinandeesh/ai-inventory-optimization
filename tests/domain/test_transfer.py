import pytest

from app.domain.exceptions import (
    InvalidInventoryError,
    InvalidSafetyStockError,
    InvalidTransferError,
)
from app.domain.transfer import (
    calculate_estimated_transfer_cost,
    calculate_feasible_transfer_quantity,
    calculate_source_surplus,
    is_candidate_feasible,
)


def test_calculate_source_surplus_positive() -> None:
    assert calculate_source_surplus(
        source_available_inventory=650, source_safety_stock_units=200.0
    ) == 450


def test_calculate_source_surplus_zero_or_negative() -> None:
    assert calculate_source_surplus(
        source_available_inventory=200, source_safety_stock_units=200.0
    ) == 0
    assert calculate_source_surplus(
        source_available_inventory=150, source_safety_stock_units=200.0
    ) == 0


def test_calculate_source_surplus_invalid_inputs_raise_errors() -> None:
    with pytest.raises(InvalidInventoryError):
        calculate_source_surplus(-10, 200.0)
    with pytest.raises(InvalidSafetyStockError):
        calculate_source_surplus(650, -50.0)


def test_calculate_feasible_transfer_quantity() -> None:
    assert calculate_feasible_transfer_quantity(target_shortage_qty=180, source_surplus=450) == 180
    assert calculate_feasible_transfer_quantity(target_shortage_qty=180, source_surplus=100) == 100


def test_is_candidate_feasible_rules() -> None:
    # Valid Feasible Candidate
    assert is_candidate_feasible(
        source_dc_code="DC-IND",
        target_dc_code="DC-CHI",
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
        source_surplus=450,
        feasible_quantity=180,
        transit_days=1,
        days_to_stockout=2.5,
    ) is True

    # Same Source and Target DC
    assert is_candidate_feasible("DC-CHI", "DC-CHI", True, True, True, 450, 180, 1, 2.5) is False

    # Inactive Route / DC
    assert is_candidate_feasible("DC-IND", "DC-CHI", False, True, True, 450, 180, 1, 2.5) is False
    assert is_candidate_feasible("DC-IND", "DC-CHI", True, True, False, 450, 180, 1, 2.5) is False

    # Zero Surplus
    assert is_candidate_feasible("DC-IND", "DC-CHI", True, True, True, 0, 0, 1, 2.5) is False

    # Transit Lead Time Exactly Equal to DUS (STRICT < Requirement)
    assert is_candidate_feasible("DC-IND", "DC-CHI", True, True, True, 450, 180, 3, 3.0) is False

    # Transit Lead Time Greater than DUS (Dallas Scenario: 3 days vs 2.5 DUS)
    assert is_candidate_feasible("DC-DAL", "DC-CHI", True, True, True, 700, 180, 3, 2.5) is False


def test_calculate_estimated_transfer_cost() -> None:
    assert calculate_estimated_transfer_cost(recommended_qty=180, route_unit_cost=2.50) == 450.0
    assert calculate_estimated_transfer_cost(recommended_qty=100, route_unit_cost=7.78) == 778.0


def test_calculate_estimated_transfer_cost_invalid_inputs_raise_errors() -> None:
    with pytest.raises(InvalidTransferError):
        calculate_estimated_transfer_cost(0, 2.50)
    with pytest.raises(InvalidTransferError):
        calculate_estimated_transfer_cost(180, -1.0)
