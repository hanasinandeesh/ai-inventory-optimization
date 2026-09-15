import pytest

from app.domain.exceptions import InvalidInventoryError
from app.domain.inventory import InventoryBalance, calculate_available_inventory


def test_inventory_available_calculation_normal() -> None:
    assert calculate_available_inventory(on_hand_qty=100, reserved_qty=0) == 100
    assert calculate_available_inventory(on_hand_qty=100, reserved_qty=30) == 70


def test_inventory_available_calculation_zero() -> None:
    assert calculate_available_inventory(on_hand_qty=0, reserved_qty=0) == 0


def test_inventory_reserved_equal_on_hand() -> None:
    balance = InventoryBalance(on_hand_qty=50, reserved_qty=50)
    assert balance.available_qty == 0


def test_inventory_negative_on_hand_raises_error() -> None:
    with pytest.raises(InvalidInventoryError) as exc_info:
        InventoryBalance(on_hand_qty=-10, reserved_qty=0)
    assert "On-hand quantity cannot be negative" in str(exc_info.value)


def test_inventory_negative_reserved_raises_error() -> None:
    with pytest.raises(InvalidInventoryError) as exc_info:
        InventoryBalance(on_hand_qty=50, reserved_qty=-5)
    assert "Reserved quantity cannot be negative" in str(exc_info.value)


def test_inventory_reserved_greater_than_on_hand_raises_error() -> None:
    with pytest.raises(InvalidInventoryError) as exc_info:
        InventoryBalance(on_hand_qty=50, reserved_qty=60)
    assert "Reserved quantity (60) cannot exceed on-hand quantity (50)" in str(exc_info.value)
