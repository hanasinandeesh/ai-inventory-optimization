"""
RecommendationService implementation.
Orchestrates transfer recommendation generation for stockout risk incidents.
Coordinates candidate discovery, AI provider ranking, deterministic fallback,
post-validation, transaction persistence, and audit logging.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.domain.demand import calculate_average_daily_demand
from app.domain.enums import IncidentStatus
from app.domain.inventory import calculate_available_inventory
from app.domain.recommendation import (
    RecommendationProposal,
    select_fallback_candidate,
    validate_recommendation_proposal,
)
from app.domain.transfer import PreValidatedCandidate
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.dtos import (
    AIRecommendationInputDTO,
    AuditEventCreateData,
    RecommendationResultDTO,
    TransferRecommendationCreateData,
)
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from app.services.interfaces import (
    AIRecommendationProviderInterface,
    AuditRepositoryInterface,
    DemandRepositoryInterface,
    DistributionCenterRepositoryInterface,
    InventoryPolicyRepositoryInterface,
    InventoryRepositoryInterface,
    ProductRepositoryInterface,
    RiskIncidentRepositoryInterface,
    RouteRepositoryInterface,
    TransferRecommendationRepositoryInterface,
)
from app.services.unit_of_work import UnitOfWorkProtocol


class RecommendationService:
    """
    Application Service orchestrating AI-driven transfer recommendation generation.
    Pure application orchestration following dependency inversion.
    """

    def __init__(
        self,
        risk_repo: RiskIncidentRepositoryInterface,
        dc_repo: DistributionCenterRepositoryInterface,
        product_repo: ProductRepositoryInterface,
        inventory_repo: InventoryRepositoryInterface,
        policy_repo: InventoryPolicyRepositoryInterface,
        route_repo: RouteRepositoryInterface,
        recommendation_repo: TransferRecommendationRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        candidate_discovery_service: CandidateDiscoveryService,
        ai_provider: AIRecommendationProviderInterface,
        uow: UnitOfWorkProtocol,
        demand_repo: DemandRepositoryInterface | None = None,
    ) -> None:
        self._risk_repo = risk_repo
        self._dc_repo = dc_repo
        self._product_repo = product_repo
        self._inventory_repo = inventory_repo
        self._policy_repo = policy_repo
        self._route_repo = route_repo
        self._recommendation_repo = recommendation_repo
        self._audit_repo = audit_repo
        self._candidate_discovery_service = candidate_discovery_service
        self._ai_provider = ai_provider
        self._uow = uow
        self._demand_repo = demand_repo

    def generate_recommendation(self, incident_id: int) -> RecommendationResultDTO:
        """
        Executes the transfer recommendation generation workflow:
        1. Resolves and validates target RiskIncident (must exist and be OPEN).
        2. Resolves Target DC and Product details.
        3. Calls CandidateDiscoveryService outside any database transaction.
        4. If 0 candidates: creates NO_FEASIBLE_SOURCE_FOUND audit log and returns result.
        5. If candidates exist: constructs AIRecommendationInputDTO with business IDs only.
        6. Invokes external AI provider outside any database transaction.
        7. On AI failure (timeout, exception, malformed output, unknown candidate ID),
           falls back deterministically using prevalidated candidate list.
        8. Executes deterministic post-validation guardrails. (Validation failures raise
           RecommendationValidationError without fallback).
        9. Opens a single write UnitOfWork transaction to persist TransferRecommendation
           (with decision-time snapshots) and RECOMMENDATION_GENERATED audit log.
        10. Returns RecommendationResultDTO(has_recommendation=True, status="PROPOSED").
        """
        # 1. Resolve RiskIncident
        incident = self._risk_repo.get_by_id(incident_id)
        if incident is None:
            raise ResourceNotFoundError(f"RiskIncident '{incident_id}' not found")

        if incident.status != IncidentStatus.OPEN.value:
            raise ResourceInactiveError(
                f"RiskIncident '{incident.incident_code}' is in status "
                f"'{incident.status}', only OPEN incidents are eligible for recommendations"
            )

        # 2. Resolve Target DC & Product
        target_dc = self._dc_repo.get_by_id(incident.target_dc_id)
        if target_dc is None:
            raise ResourceNotFoundError(
                f"Target DistributionCenter ID {incident.target_dc_id} not found"
            )
        if not target_dc.is_active:
            raise ResourceInactiveError(f"Target DistributionCenter '{target_dc.code}' is inactive")

        product = self._product_repo.get_by_id(incident.product_id)
        if product is None:
            raise ResourceNotFoundError(f"Product ID {incident.product_id} not found")

        # 3. Candidate Discovery (Executed OUTSIDE any database transaction)
        discovery_result = self._candidate_discovery_service.discover_feasible_candidates(
            incident.id
        )

        # 4. Handle zero feasible candidates case
        if not discovery_result.feasible_candidates:
            with self._uow:
                self._audit_repo.create_audit_event(
                    AuditEventCreateData(
                        incident_id=incident.id,
                        action="NO_FEASIBLE_SOURCE_FOUND",
                    )
                )
                self._uow.commit()

            return RecommendationResultDTO(
                has_recommendation=False,
                status="NO_FEASIBLE_SOURCE",
                incident_id=incident.id,
                target_dc_id=target_dc.id,
                target_dc_code=target_dc.code,
                product_id=incident.product_id,
                product_sku=product.sku,
            )

        # 5. Candidates exist -> Construct AI input using business identifiers ONLY
        candidate_map = {c.candidate_id: c for c in discovery_result.feasible_candidates}
        ai_input = AIRecommendationInputDTO(
            incident_code=incident.incident_code,
            target_dc_code=target_dc.code,
            product_sku=product.sku,
            product_name=product.name,
            category=product.category,
            days_to_stockout=incident.days_to_stockout,
            shortage_qty=int(round(incident.shortage_qty)),
            severity=incident.severity,
            prevalidated_candidates=discovery_result.feasible_candidates,
        )

        selected_candidate: PreValidatedCandidate | None = None
        recommendation_source: str = "AI"
        rationale: str = ""

        # 6. Call AI provider OUTSIDE any database transaction
        try:
            ai_output = self._ai_provider.generate_recommendation(ai_input)
            if (
                ai_output is not None
                and hasattr(ai_output, "selected_candidate_id")
                and isinstance(ai_output.selected_candidate_id, str)
                and ai_output.selected_candidate_id in candidate_map
            ):
                selected_candidate = candidate_map[ai_output.selected_candidate_id]
                recommendation_source = "AI"
                rationale = (
                    ai_output.rationale
                    if (hasattr(ai_output, "rationale") and ai_output.rationale)
                    else "AI selected transfer source candidate"
                )
            else:
                # Unknown candidate ID or malformed output -> Trigger fallback
                selected_candidate = select_fallback_candidate(discovery_result.feasible_candidates)
                recommendation_source = "DETERMINISTIC_FALLBACK"
                reason = (
                    "Unknown candidate ID"
                    if (ai_output and hasattr(ai_output, "selected_candidate_id"))
                    else "Malformed AI output"
                )
                rationale = (
                    f"[DETERMINISTIC_FALLBACK] {reason}. "
                    f"Selected fallback candidate: {selected_candidate.source_dc_code}"
                )
        except Exception as exc:
            # AI provider exception or timeout -> Trigger fallback
            selected_candidate = select_fallback_candidate(discovery_result.feasible_candidates)
            recommendation_source = "DETERMINISTIC_FALLBACK"
            rationale = (
                f"[DETERMINISTIC_FALLBACK] AI provider error: {exc}. "
                f"Selected fallback candidate: {selected_candidate.source_dc_code}"
            )

        # 7. Deterministic Post-Validation
        source_dc = self._dc_repo.get_by_code(selected_candidate.source_dc_code)
        if source_dc is None:
            raise ResourceNotFoundError(
                f"Source DistributionCenter '{selected_candidate.source_dc_code}' not found"
            )

        route = self._route_repo.get_active_route(source_dc.id, target_dc.id)
        source_balance = self._inventory_repo.get_balance(source_dc.id, incident.product_id)
        source_policy = self._policy_repo.get_active_policy(source_dc.id, incident.product_id)

        source_available = (
            calculate_available_inventory(source_balance.on_hand_qty, source_balance.reserved_qty)
            if source_balance
            else 0
        )

        if source_policy and self._demand_repo:
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
                source_safety_stock_units = float(source_policy.safety_stock_days)
        elif source_policy:
            source_safety_stock_units = float(source_policy.safety_stock_days)
        else:
            source_safety_stock_units = float(
                source_available - selected_candidate.available_surplus
            )

        proposal = RecommendationProposal(
            selected_candidate_id=selected_candidate.candidate_id,
            source_dc_code=selected_candidate.source_dc_code,
            target_dc_code=target_dc.code,
            recommended_qty=selected_candidate.feasible_quantity,
            target_shortage_qty=int(round(incident.shortage_qty)),
            source_surplus=selected_candidate.available_surplus,
            source_available_qty=source_available,
            source_safety_stock_units=source_safety_stock_units,
            transit_days=selected_candidate.transit_days,
            route_unit_cost=selected_candidate.route_unit_cost,
            estimated_total_cost=selected_candidate.estimated_total_cost,
            days_to_stockout=incident.days_to_stockout,
            source_is_active=source_dc.is_active,
            target_is_active=target_dc.is_active,
            route_is_active=route is not None and route.is_active,
        )

        # Execute guardrail validation. If validation fails, raises RecommendationValidationError
        validate_recommendation_proposal(proposal, discovery_result.feasible_candidates)

        # 8. Single Persistence Transaction (Write UnitOfWork)
        recommendation_code = f"REC-{incident.incident_code}"

        create_data = TransferRecommendationCreateData(
            recommendation_code=recommendation_code,
            incident_id=incident.id,
            source_dc_id=source_dc.id,
            target_dc_id=target_dc.id,
            product_id=incident.product_id,
            recommended_qty=selected_candidate.feasible_quantity,
            feasible_qty_snapshot=selected_candidate.feasible_quantity,
            source_surplus_snapshot=selected_candidate.available_surplus,
            transit_days_snapshot=selected_candidate.transit_days,
            route_unit_cost_snapshot=Decimal(str(selected_candidate.route_unit_cost)),
            estimated_cost_snapshot=Decimal(str(selected_candidate.estimated_total_cost)),
            rationale=rationale,
            recommendation_source=recommendation_source,
            status="PROPOSED",
        )

        with self._uow:
            created_rec = self._recommendation_repo.create_recommendation(create_data)
            self._audit_repo.create_audit_event(
                AuditEventCreateData(
                    incident_id=incident.id,
                    action="RECOMMENDATION_GENERATED",
                    recommendation_id=created_rec.id,
                )
            )
            self._uow.commit()

        # 9. Return Result DTO
        return RecommendationResultDTO(
            has_recommendation=True,
            status="PROPOSED",
            recommendation_id=created_rec.id,
            recommendation_code=created_rec.recommendation_code,
            incident_id=incident.id,
            source_dc_id=source_dc.id,
            source_dc_code=source_dc.code,
            target_dc_id=target_dc.id,
            target_dc_code=target_dc.code,
            product_id=incident.product_id,
            product_sku=product.sku,
            recommended_qty=selected_candidate.feasible_quantity,
            estimated_total_cost=Decimal(str(selected_candidate.estimated_total_cost)),
            recommendation_source=recommendation_source,
            rationale=rationale,
            created_at=created_rec.created_at,
        )
