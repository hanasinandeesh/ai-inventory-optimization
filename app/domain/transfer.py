from dataclasses import dataclass

from app.domain.exceptions import (
    InvalidInventoryError,
    InvalidSafetyStockError,
    InvalidTransferError,
)


@dataclass(frozen=True)
class PreValidatedCandidate:
    """Dataclass representing a pre-validated feasible transfer candidate source DC."""

    candidate_id: str
    source_dc_code: str
    available_surplus: int
    feasible_quantity: int
    transit_days: int
    route_unit_cost: float
    estimated_total_cost: float
    can_arrive_before_stockout: bool


def calculate_source_surplus(
    source_available_inventory: int, source_safety_stock_units: float
) -> int:
    """
    Computes available surplus stock at candidate source DC.
    Formula: max(0, source_available_inventory - source_safety_stock_units)
    """
    if source_available_inventory < 0:
        raise InvalidInventoryError(
            f"Source available inventory cannot be negative (got {source_available_inventory})"
        )
    if source_safety_stock_units < 0:
        raise InvalidSafetyStockError(
            f"Source safety stock units cannot be negative (got {source_safety_stock_units})"
        )

    surplus = source_available_inventory - source_safety_stock_units
    return max(0, int(round(surplus)))


def calculate_feasible_transfer_quantity(target_shortage_qty: int, source_surplus: int) -> int:
    """
    Computes maximum feasible transfer quantity between target and candidate source.
    Formula: min(target_shortage_qty, source_surplus)
    """
    if target_shortage_qty < 0:
        raise InvalidTransferError(
            f"Target shortage quantity cannot be negative (got {target_shortage_qty})"
        )
    if source_surplus < 0:
        raise InvalidTransferError(f"Source surplus cannot be negative (got {source_surplus})")

    return min(target_shortage_qty, source_surplus)


def is_candidate_feasible(
    source_dc_code: str,
    target_dc_code: str,
    source_is_active: bool,
    target_is_active: bool,
    route_is_active: bool,
    source_surplus: int,
    feasible_quantity: int,
    transit_days: int,
    days_to_stockout: float,
) -> bool:
    """
    Evaluates candidate feasibility according to deterministic domain rules:
    - source DC != target DC
    - source DC is active
    - target DC is active
    - route is active
    - source surplus > 0
    - feasible quantity > 0
    - transit_days < days_to_stockout (STRICT < requirement)
    """
    if source_dc_code == target_dc_code:
        return False
    if not source_is_active or not target_is_active or not route_is_active:
        return False
    if source_surplus <= 0 or feasible_quantity <= 0:
        return False
    if transit_days >= days_to_stockout:
        return False

    return True


def calculate_estimated_transfer_cost(recommended_qty: int, route_unit_cost: float) -> float:
    """
    Computes estimated total transfer cost.
    Formula: recommended_qty * route_unit_cost
    The LLM is NEVER authoritative for transfer costs.
    """
    if recommended_qty <= 0:
        raise InvalidTransferError(
            f"Recommended quantity must be strictly positive (got {recommended_qty})"
        )
    if route_unit_cost < 0:
        raise InvalidTransferError(f"Route unit cost cannot be negative (got {route_unit_cost})")

    return round(float(recommended_qty * route_unit_cost), 2)
