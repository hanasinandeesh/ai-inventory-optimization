import pytest

from app.domain.exceptions import (
    InfeasibleTransferError,
    RecommendationValidationError,
)
from app.domain.recommendation import (
    RecommendationProposal,
    select_fallback_candidate,
    validate_recommendation_proposal,
)
from app.domain.transfer import PreValidatedCandidate


@pytest.fixture
def indy_candidate() -> PreValidatedCandidate:
    return PreValidatedCandidate(
        candidate_id="cand_ind_01",
        source_dc_code="DC-IND",
        available_surplus=450,
        feasible_quantity=180,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=450.0,
        can_arrive_before_stockout=True,
    )


@pytest.fixture
def valid_proposal() -> RecommendationProposal:
    return RecommendationProposal(
        selected_candidate_id="cand_ind_01",
        source_dc_code="DC-IND",
        target_dc_code="DC-CHI",
        recommended_qty=180,
        target_shortage_qty=180,
        source_surplus=450,
        source_available_qty=650,
        source_safety_stock_units=200.0,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=450.0,
        days_to_stockout=2.5,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
    )


def test_select_fallback_candidate_selection_policy(
    indy_candidate: PreValidatedCandidate,
) -> None:
    slower_candidate = PreValidatedCandidate(
        candidate_id="cand_slow_02",
        source_dc_code="DC-SLOW",
        available_surplus=500,
        feasible_quantity=180,
        transit_days=2,
        route_unit_cost=2.00,
        estimated_total_cost=360.0,
        can_arrive_before_stockout=True,
    )

    # Policy Rule: 1-day transit prioritized over 2-day transit despite lower cost
    selected = select_fallback_candidate([slower_candidate, indy_candidate])
    assert selected.candidate_id == "cand_ind_01"


def test_select_fallback_candidate_empty_list_raises_error() -> None:
    with pytest.raises(InfeasibleTransferError):
        select_fallback_candidate([])


def test_validate_recommendation_proposal_success(
    valid_proposal: RecommendationProposal, indy_candidate: PreValidatedCandidate
) -> None:
    assert validate_recommendation_proposal(valid_proposal, [indy_candidate]) is True


def test_validate_recommendation_unlisted_candidate_raises_error(
    valid_proposal: RecommendationProposal,
) -> None:
    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_recommendation_proposal(valid_proposal, [])
    assert "is not in pre-validated candidates list" in str(exc_info.value)


def test_validate_recommendation_depletes_source_safety_stock(
    valid_proposal: RecommendationProposal, indy_candidate: PreValidatedCandidate
) -> None:
    invalid_proposal = RecommendationProposal(
        selected_candidate_id="cand_ind_01",
        source_dc_code="DC-IND",
        target_dc_code="DC-CHI",
        recommended_qty=500,  # Exceeds surplus of 450 (650 - 500 = 150 < 200 safety stock)
        target_shortage_qty=500,
        source_surplus=450,
        source_available_qty=650,
        source_safety_stock_units=200.0,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=1250.0,
        days_to_stockout=2.5,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
    )
    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_recommendation_proposal(invalid_proposal, [indy_candidate])
    assert "depletes source stock" in str(exc_info.value)


def test_validate_recommendation_transit_exceeds_dus(
    valid_proposal: RecommendationProposal, indy_candidate: PreValidatedCandidate
) -> None:
    invalid_proposal = RecommendationProposal(
        selected_candidate_id="cand_ind_01",
        source_dc_code="DC-IND",
        target_dc_code="DC-CHI",
        recommended_qty=180,
        target_shortage_qty=180,
        source_surplus=450,
        source_available_qty=650,
        source_safety_stock_units=200.0,
        transit_days=3,  # 3 days >= 2.5 DUS
        route_unit_cost=2.50,
        estimated_total_cost=450.0,
        days_to_stockout=2.5,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
    )
    with pytest.raises(RecommendationValidationError) as exc_info:
        validate_recommendation_proposal(invalid_proposal, [indy_candidate])
    assert "is not less than days to stockout" in str(exc_info.value)
