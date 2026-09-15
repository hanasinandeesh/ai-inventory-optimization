import pytest

from app.domain.demand import calculate_average_daily_demand
from app.domain.exceptions import InvalidDemandError


def test_average_daily_demand_constant() -> None:
    demands = [40] * 14
    assert calculate_average_daily_demand(demands) == 40.0


def test_average_daily_demand_varying() -> None:
    demands = [30, 50, 40, 40, 35, 45, 40, 40, 30, 50, 40, 40, 35, 45]
    assert calculate_average_daily_demand(demands) == 40.0


def test_average_daily_demand_zero() -> None:
    demands = [0] * 14
    assert calculate_average_daily_demand(demands) == 0.0


def test_average_daily_demand_invalid_length_raises_error() -> None:
    with pytest.raises(InvalidDemandError) as exc_info:
        calculate_average_daily_demand([40] * 10)
    assert "requires exactly 14 daily demand entries" in str(exc_info.value)


def test_average_daily_demand_negative_value_raises_error() -> None:
    demands = [40] * 13 + [-5]
    with pytest.raises(InvalidDemandError) as exc_info:
        calculate_average_daily_demand(demands)
    assert "Daily demand quantity at index 13 cannot be negative" in str(exc_info.value)
