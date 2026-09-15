from dataclasses import dataclass

from app.domain.exceptions import InvalidInventoryError


@dataclass(frozen=True)
class InventoryBalance:
    """
    Value object representing inventory state for a SKU at a facility.
    Available Inventory = on_hand_qty - reserved_qty
    """

    on_hand_qty: int
    reserved_qty: int

    def __post_init__(self) -> None:
        if self.on_hand_qty < 0:
            raise InvalidInventoryError(
                f"On-hand quantity cannot be negative (got {self.on_hand_qty})"
            )
        if self.reserved_qty < 0:
            raise InvalidInventoryError(
                f"Reserved quantity cannot be negative (got {self.reserved_qty})"
            )
        if self.reserved_qty > self.on_hand_qty:
            raise InvalidInventoryError(
                f"Reserved quantity ({self.reserved_qty}) cannot exceed "
                f"on-hand quantity ({self.on_hand_qty})"
            )

    @property
    def available_qty(self) -> int:
        return self.on_hand_qty - self.reserved_qty


def calculate_available_inventory(on_hand_qty: int, reserved_qty: int) -> int:
    """
    Deterministically computes available inventory.
    Formula: Available Inventory = on_hand_qty - reserved_qty
    """
    balance = InventoryBalance(on_hand_qty=on_hand_qty, reserved_qty=reserved_qty)
    return balance.available_qty
