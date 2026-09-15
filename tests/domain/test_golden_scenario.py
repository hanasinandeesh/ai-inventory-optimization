from datetime import date

from app.domain.demand import calculate_average_daily_demand
from app.domain.enums import RiskSeverity
from app.domain.inventory import calculate_available_inventory
from app.domain.recommendation import (
    RecommendationProposal,
    select_fallback_candidate,
    validate_recommendation_proposal,
)
from app.domain.risk import evaluate_stockout_risk
from app.domain.transfer import (
    PreValidatedCandidate,
    calculate_estimated_transfer_cost,
    calculate_feasible_transfer_quantity,
    calculate_source_surplus,
    is_candidate_feasible,
)


def test_golden_scenario_chicago_seafood_imbalance() -> None:
    """
    Validates the end-to-end Midwestern Frozen Seafood Imbalance Golden Scenario
    using pure deterministic domain logic.
    """
    # -------------------------------------------------------------------------
    # 1. Target DC (Chicago) Stockout Risk Assessment
    # -------------------------------------------------------------------------
    target_dc_code = "DC-CHI"
    detection_date = date(2026, 9, 16)

    chicago_on_hand = 100
    chicago_reserved = 0
    chicago_available = calculate_available_inventory(chicago_on_hand, chicago_reserved)
    assert chicago_available == 100

    chicago_demand_history = [40] * 14
    chicago_avg_demand = calculate_average_daily_demand(chicago_demand_history)
    assert chicago_avg_demand == 40.0

    chicago_safety_stock_days = 7

    risk_assessment = evaluate_stockout_risk(
        available_inventory=chicago_available,
        average_daily_demand=chicago_avg_demand,
        safety_stock_days=chicago_safety_stock_days,
        detection_date=detection_date,
    )

    assert risk_assessment.available_inventory == 100
    assert risk_assessment.average_daily_demand == 40.0
    assert risk_assessment.days_to_stockout == 2.5
    assert risk_assessment.target_safety_stock_units == 280.0
    assert risk_assessment.shortage_quantity == 180
    assert risk_assessment.severity == RiskSeverity.CRITICAL
    assert risk_assessment.projected_stockout_date == date(2026, 9, 18)

    # -------------------------------------------------------------------------
    # 2. Candidate Source 1: Indianapolis Evaluation
    # -------------------------------------------------------------------------
    indy_dc_code = "DC-IND"
    indy_available = 650
    indy_safety_stock = 200.0
    indy_surplus = calculate_source_surplus(indy_available, indy_safety_stock)
    assert indy_surplus == 450

    indy_transit_days = 1
    indy_unit_cost = 2.50

    indy_feasible_qty = calculate_feasible_transfer_quantity(
        target_shortage_qty=risk_assessment.shortage_quantity,
        source_surplus=indy_surplus,
    )
    assert indy_feasible_qty == 180

    indy_is_feasible = is_candidate_feasible(
        source_dc_code=indy_dc_code,
        target_dc_code=target_dc_code,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
        source_surplus=indy_surplus,
        feasible_quantity=indy_feasible_qty,
        transit_days=indy_transit_days,
        days_to_stockout=risk_assessment.days_to_stockout,
    )
    assert indy_is_feasible is True

    indy_estimated_cost = calculate_estimated_transfer_cost(
        recommended_qty=indy_feasible_qty, route_unit_cost=indy_unit_cost
    )
    assert indy_estimated_cost == 450.0

    indy_candidate = PreValidatedCandidate(
        candidate_id="cand_ind_01",
        source_dc_code=indy_dc_code,
        available_surplus=indy_surplus,
        feasible_quantity=indy_feasible_qty,
        transit_days=indy_transit_days,
        route_unit_cost=indy_unit_cost,
        estimated_total_cost=indy_estimated_cost,
        can_arrive_before_stockout=True,
    )

    # -------------------------------------------------------------------------
    # 3. Candidate Source 2: Dallas Evaluation
    # -------------------------------------------------------------------------
    dallas_dc_code = "DC-DAL"
    dallas_available = 1000
    dallas_safety_stock = 300.0
    dallas_surplus = calculate_source_surplus(dallas_available, dallas_safety_stock)
    assert dallas_surplus == 700

    dallas_transit_days = 3

    dallas_feasible_qty = calculate_feasible_transfer_quantity(
        target_shortage_qty=risk_assessment.shortage_quantity,
        source_surplus=dallas_surplus,
    )

    # Dallas transit lead time (3 days) >= Days to Stockout (2.5 days) -> Infeasible
    dallas_is_feasible = is_candidate_feasible(
        source_dc_code=dallas_dc_code,
        target_dc_code=target_dc_code,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
        source_surplus=dallas_surplus,
        feasible_quantity=dallas_feasible_qty,
        transit_days=dallas_transit_days,
        days_to_stockout=risk_assessment.days_to_stockout,
    )
    assert dallas_is_feasible is False

    # -------------------------------------------------------------------------
    # 4. Candidate Discovery & Selection Assembly
    # -------------------------------------------------------------------------
    # Pre-validated candidates list contains ONLY feasible candidates (Indianapolis)
    prevalidated_candidates = [indy_candidate]
    assert len(prevalidated_candidates) == 1

    selected_candidate = select_fallback_candidate(prevalidated_candidates)
    assert selected_candidate.source_dc_code == "DC-IND"
    assert selected_candidate.feasible_quantity == 180
    assert selected_candidate.estimated_total_cost == 450.0

    # -------------------------------------------------------------------------
    # 5. Deterministic Recommendation Post-Validation
    # -------------------------------------------------------------------------
    recommendation_proposal = RecommendationProposal(
        selected_candidate_id=selected_candidate.candidate_id,
        source_dc_code=selected_candidate.source_dc_code,
        target_dc_code=target_dc_code,
        recommended_qty=selected_candidate.feasible_quantity,
        target_shortage_qty=risk_assessment.shortage_quantity,
        source_surplus=indy_surplus,
        source_available_qty=indy_available,
        source_safety_stock_units=indy_safety_stock,
        transit_days=indy_transit_days,
        route_unit_cost=indy_unit_cost,
        estimated_total_cost=indy_estimated_cost,
        days_to_stockout=risk_assessment.days_to_stockout,
        source_is_active=True,
        target_is_active=True,
        route_is_active=True,
    )

    validation_result = validate_recommendation_proposal(
        proposal=recommendation_proposal,
        prevalidated_candidates=prevalidated_candidates,
    )
    assert validation_result is True
