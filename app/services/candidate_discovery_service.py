"""
CandidateDiscoveryService implementation.
Orchestrates deterministic candidate source DC discovery for a given RiskIncident.
Applies strict arrival feasibility and domain transfer rules.
"""

from datetime import date, timedelta

from app.domain.demand import calculate_average_daily_demand
from app.domain.enums import IncidentStatus
from app.domain.inventory import calculate_available_inventory
from app.domain.transfer import (
    PreValidatedCandidate,
    calculate_estimated_transfer_cost,
    calculate_feasible_transfer_quantity,
    calculate_source_surplus,
    is_candidate_feasible,
)
from app.services.dtos import CandidateDiscoveryResultDTO
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from app.services.interfaces import (
    DemandRepositoryInterface,
    DistributionCenterRepositoryInterface,
    InventoryPolicyRepositoryInterface,
    InventoryRepositoryInterface,
    RiskIncidentRepositoryInterface,
    RouteRepositoryInterface,
)


class CandidateDiscoveryService:
    """
    Application Service discovering pre-validated feasible candidate source DCs for a risk incident.
    Pure deterministic orchestration using domain rules and repository protocols.
    """

    def __init__(
        self,
        risk_repo: RiskIncidentRepositoryInterface,
        dc_repo: DistributionCenterRepositoryInterface,
        inventory_repo: InventoryRepositoryInterface,
        demand_repo: DemandRepositoryInterface,
        policy_repo: InventoryPolicyRepositoryInterface,
        route_repo: RouteRepositoryInterface,
    ) -> None:
        self._risk_repo = risk_repo
        self._dc_repo = dc_repo
        self._inventory_repo = inventory_repo
        self._demand_repo = demand_repo
        self._policy_repo = policy_repo
        self._route_repo = route_repo

    def discover_feasible_candidates(
        self, incident_id_or_code: int | str
    ) -> CandidateDiscoveryResultDTO:
        """
        Executes candidate source discovery use-case:
        1. Resolves and validates target RiskIncident (must exist and be OPEN).
        2. Resolves target DC.
        3. Fetches active candidate source DCs excluding target DC.
        4. For each active candidate source DC:
           - Retrieves inventory balance and calculates available inventory.
           - Retrieves active inventory policy and calculates target safety stock units.
           - Calculates source surplus using domain rule `calculate_source_surplus`.
           - Retrieves active transportation route to target DC.
           - Enforces strict arrival feasibility (`transit_days < days_to_stockout`).
           - Calculates feasible transfer quantity and estimated total transfer cost.
        5. Returns ONLY pre-validated feasible candidates.
        """
        # 1. Resolve RiskIncident
        if isinstance(incident_id_or_code, int):
            incident = self._risk_repo.get_by_id(incident_id_or_code)
        else:
            incident = self._risk_repo.get_by_code(incident_id_or_code)

        if incident is None:
            raise ResourceNotFoundError(f"RiskIncident '{incident_id_or_code}' not found")

        if incident.status != IncidentStatus.OPEN.value:
            raise ResourceInactiveError(
                f"RiskIncident '{incident.incident_code}' is in status "
                f"'{incident.status}', only OPEN incidents are eligible for discovery"
            )

        # 2. Resolve Target DC
        target_dc = self._dc_repo.get_by_id(incident.target_dc_id)
        if target_dc is None:
            raise ResourceNotFoundError(
                f"Target DistributionCenter ID {incident.target_dc_id} not found"
            )

        if not target_dc.is_active:
            raise ResourceInactiveError(f"Target DistributionCenter '{target_dc.code}' is inactive")

        target_shortage_qty = int(round(incident.shortage_qty))
        days_to_stockout = incident.days_to_stockout

        # 3. Retrieve eligible active source DCs (excluding target DC)
        active_source_dcs = self._dc_repo.get_active_source_dcs(exclude_dc_id=target_dc.id)

        feasible_candidates: list[PreValidatedCandidate] = []

        # 4. Evaluate each candidate source DC
        for source_dc in active_source_dcs:
            # a. Retrieve source inventory balance
            source_balance = self._inventory_repo.get_balance(
                dc_id=source_dc.id, product_id=incident.product_id
            )
            if source_balance is None or source_balance.on_hand_qty <= 0:
                continue

            source_available = calculate_available_inventory(
                on_hand_qty=source_balance.on_hand_qty,
                reserved_qty=source_balance.reserved_qty,
            )
            if source_available <= 0:
                continue

            # b. Retrieve source inventory policy
            source_policy = self._policy_repo.get_active_policy(
                dc_id=source_dc.id, product_id=incident.product_id
            )
            if source_policy is None or not source_policy.is_active:
                continue

            # Calculate source safety stock units
            # Fetch demand signals for candidate source DC to compute source average daily demand
            reference_date = date.today()
            start_date = reference_date - timedelta(days=13)
            source_demand_signals = self._demand_repo.get_daily_demand_signals(
                dc_id=source_dc.id,
                product_id=incident.product_id,
                start_date=start_date,
                end_date=reference_date,
            )

            if len(source_demand_signals) == 14:
                source_avg_demand = calculate_average_daily_demand(
                    [s.daily_demand_qty for s in source_demand_signals]
                )
                source_safety_stock_units = source_policy.safety_stock_days * source_avg_demand
            else:
                # If 14-day signals unavailable for candidate, use safety_stock_days directly
                source_safety_stock_units = source_policy.safety_stock_days

            # c. Calculate source surplus
            source_surplus = calculate_source_surplus(
                source_available_inventory=source_available,
                source_safety_stock_units=source_safety_stock_units,
            )
            if source_surplus <= 0:
                continue

            # d. Retrieve active transportation route from source to target
            route = self._route_repo.get_active_route(
                source_dc_id=source_dc.id, target_dc_id=target_dc.id
            )
            if route is None or not route.is_active:
                continue

            # e. Calculate feasible transfer quantity
            feasible_qty = calculate_feasible_transfer_quantity(
                target_shortage_qty=target_shortage_qty,
                source_surplus=source_surplus,
            )
            if feasible_qty <= 0:
                continue

            # f. Enforce deterministic arrival feasibility (transit_days < days_to_stockout)
            candidate_is_feasible = is_candidate_feasible(
                source_dc_code=source_dc.code,
                target_dc_code=target_dc.code,
                source_is_active=source_dc.is_active,
                target_is_active=target_dc.is_active,
                route_is_active=route.is_active,
                source_surplus=source_surplus,
                feasible_quantity=feasible_qty,
                transit_days=route.transit_days,
                days_to_stockout=days_to_stockout,
            )
            if not candidate_is_feasible:
                continue

            # g. Calculate estimated transfer cost
            estimated_cost = calculate_estimated_transfer_cost(
                recommended_qty=feasible_qty,
                route_unit_cost=route.cost_per_unit,
            )

            # h. Construct PreValidatedCandidate
            can_arrive = route.transit_days < days_to_stockout
            candidate_id = f"CAND-{source_dc.code}-{target_dc.code}"

            candidate = PreValidatedCandidate(
                candidate_id=candidate_id,
                source_dc_code=source_dc.code,
                available_surplus=source_surplus,
                feasible_quantity=feasible_qty,
                transit_days=route.transit_days,
                route_unit_cost=route.cost_per_unit,
                estimated_total_cost=estimated_cost,
                can_arrive_before_stockout=can_arrive,
            )

            feasible_candidates.append(candidate)

        return CandidateDiscoveryResultDTO(
            incident_id=incident.id,
            incident_code=incident.incident_code,
            target_dc_id=target_dc.id,
            target_dc_code=target_dc.code,
            product_id=incident.product_id,
            target_shortage_qty=target_shortage_qty,
            days_to_stockout=days_to_stockout,
            feasible_candidates=feasible_candidates,
        )
