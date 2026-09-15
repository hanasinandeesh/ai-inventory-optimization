from collections.abc import Sequence

from app.domain.exceptions import InvalidDemandError

REQUIRED_DEMAND_WINDOW_DAYS: int = 14


def calculate_average_daily_demand(daily_demands: Sequence[int]) -> float:
    """
    Deterministically computes average daily demand rate over a 14-day window.
    Formula: sum(last 14 daily demand quantities) / 14.0

    Rejects incomplete series or negative values explicitly.
    """
    if len(daily_demands) != REQUIRED_DEMAND_WINDOW_DAYS:
        raise InvalidDemandError(
            f"V1 demand calculation requires exactly {REQUIRED_DEMAND_WINDOW_DAYS} "
            f"daily demand entries (got {len(daily_demands)})"
        )

    for idx, qty in enumerate(daily_demands):
        if qty < 0:
            raise InvalidDemandError(
                f"Daily demand quantity at index {idx} cannot be negative (got {qty})"
            )

    return sum(daily_demands) / float(REQUIRED_DEMAND_WINDOW_DAYS)
