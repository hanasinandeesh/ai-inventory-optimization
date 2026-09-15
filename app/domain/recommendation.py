from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.exceptions import (
    InfeasibleTransferError,
    RecommendationValidationError,
)
from app.domain.transfer import PreValidatedCandidate


@dataclass(frozen=True)
class RecommendationProposal:
    """Dataclass holding candidate recommendation proposal before post-validation."""

    selected_candidate_id: str
    source_dc_code: str
    target_dc_code: str
    recommended_qty: int
    target_shortage_qty: int
    source_surplus: int
    source_available_qty: int
    source_safety_stock_units: float
    transit_days: int
    route_unit_cost: float
    estimated_total_cost: float
    days_to_stockout: float
    source_is_active: bool
    target_is_active: bool
    route_is_active: bool


def select_fallback_candidate(
    prevalidated_candidates: Sequence[PreValidatedCandidate],
) -> PreValidatedCandidate:
    """
    Selects the recommended candidate source DC using the
    hierarchical deterministic business policy:
    1. Ability to arrive before stockout (can_arrive_before_stockout == True)
    2. Shorter transit lead time (transit_days)
    3. Lower estimated transfer cost (estimated_total_cost)
    4. Larger remaining source surplus buffer (available_surplus)
    """
    if not prevalidated_candidates:
        raise InfeasibleTransferError(
            "No pre-validated feasible candidate source DCs "
            "available for selection"
        )

    # Sort candidates by business ranking policy
    sorted_candidates = sorted(
        prevalidated_candidates,
        key=lambda c: (
            not c.can_arrive_before_stockout,  # True (0) prioritized over False (1)
            c.transit_days,                    # Shorter transit time
            c.estimated_total_cost,             # Lower total cost
            -c.available_surplus,              # Higher surplus
        ),
    )
    return sorted_candidates[0]


def validate_recommendation_proposal(
    proposal: RecommendationProposal,
    prevalidated_candidates: Sequence[PreValidatedCandidate],
) -> bool:
    """
    Executes 11 deterministic guardrail checks on a proposed recommendation:
    1. Candidate exists in pre-validated candidates list.
    2. Source DC != Target DC.
    3. Source, Target, and Route are all active.
    4. Source surplus > 0.
    5. Source safety stock is preserved post-transfer.
    6. Recommended quantity > 0.
    7. Recommended quantity <= Target shortage quantity.
    8. Recommended quantity <= Source surplus.
    9. Estimated cost matches exact calculation.
    10. Transit days < days to stockout (STRICT <).
    11. Candidate arrival is feasible before stockout.
    """
    candidate_map = {c.candidate_id: c for c in prevalidated_candidates}
    if proposal.selected_candidate_id not in candidate_map:
        raise RecommendationValidationError(
            f"Selected candidate '{proposal.selected_candidate_id}' "
            "is not in pre-validated candidates list"
        )

    matched_candidate = candidate_map[proposal.selected_candidate_id]

    if proposal.source_dc_code == proposal.target_dc_code:
        raise RecommendationValidationError("Source DC cannot equal Target DC")

    if not proposal.source_is_active:
        raise RecommendationValidationError(f"Source DC '{proposal.source_dc_code}' is inactive")
    if not proposal.target_is_active:
        raise RecommendationValidationError(f"Target DC '{proposal.target_dc_code}' is inactive")
    if not proposal.route_is_active:
        raise RecommendationValidationError("Route between Source and Target DC is inactive")

    if proposal.source_surplus <= 0:
        raise RecommendationValidationError(
            f"Source DC surplus must be positive (got {proposal.source_surplus})"
        )

    # Safety Stock Preservation Check
    post_transfer_stock = proposal.source_available_qty - proposal.recommended_qty
    if post_transfer_stock < proposal.source_safety_stock_units:
        raise RecommendationValidationError(
            f"Transfer of {proposal.recommended_qty} units depletes "
            f"source stock ({post_transfer_stock}) below safety "
            f"stock target ({proposal.source_safety_stock_units})"
        )

    if proposal.recommended_qty <= 0:
        raise RecommendationValidationError("Recommended quantity must be strictly positive")

    if proposal.recommended_qty > proposal.target_shortage_qty:
        raise RecommendationValidationError(
            f"Recommended quantity ({proposal.recommended_qty}) exceeds shortage quantity "
            f"({proposal.target_shortage_qty})"
        )

    if proposal.recommended_qty > proposal.source_surplus:
        raise RecommendationValidationError(
            f"Recommended quantity ({proposal.recommended_qty}) exceeds source surplus "
            f"({proposal.source_surplus})"
        )

    expected_cost = round(proposal.recommended_qty * proposal.route_unit_cost, 2)
    if round(proposal.estimated_total_cost, 2) != expected_cost:
        raise RecommendationValidationError(
            f"Estimated total cost ({proposal.estimated_total_cost}) does not match "
            f"calculated cost ({expected_cost})"
        )

    if proposal.transit_days >= proposal.days_to_stockout:
        raise RecommendationValidationError(
            f"Transit lead time ({proposal.transit_days} days) is not less than days to stockout "
            f"({proposal.days_to_stockout} days)"
        )

    if not matched_candidate.can_arrive_before_stockout:
        raise RecommendationValidationError(
            "Selected candidate cannot arrive before stockout occurs"
        )

    return True
