"""
Tests for RecommendationService application service.
Verifies use-case orchestration, AI recommendation provider interaction,
deterministic fallback policy, post-validation guardrails, snapshot correctness,
transaction boundary isolation, zero-candidate audit handling, and Golden Scenario E2E execution.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Self

import pytest

from app.domain.exceptions import RecommendationValidationError
from app.domain.transfer import PreValidatedCandidate
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.dtos import (
    AIRecommendationInputDTO,
    AIRecommendationOutputDTO,
    AuditEventCreateData,
    AuditEventDTO,
    DCRouteDTO,
    DistributionCenterDTO,
    InventoryBalanceDTO,
    InventoryPolicyDTO,
    ProductDTO,
    RiskIncidentDTO,
    TransferRecommendationCreateData,
    TransferRecommendationDTO,
)
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from app.services.recommendation_service import RecommendationService

# --- Fake UnitOfWork and Repositories ---


class FakeUnitOfWork:
    """Fake UnitOfWork tracking commit, rollback, and active transaction state."""

    def __init__(self) -> None:
        self.in_transaction = False
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self) -> Self:
        self.in_transaction = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        self.in_transaction = False
        if exc_type is not None:
            self.rollback()


class FakeRiskIncidentRepository:
    def __init__(self, incidents: list[RiskIncidentDTO] | None = None) -> None:
        self._incidents = incidents or []

    def get_by_id(self, incident_id: int) -> RiskIncidentDTO | None:
        return next((i for i in self._incidents if i.id == incident_id), None)

    def get_by_code(self, incident_code: str) -> RiskIncidentDTO | None:
        return next((i for i in self._incidents if i.incident_code == incident_code), None)


class FakeDistributionCenterRepository:
    def __init__(self, dcs: list[DistributionCenterDTO] | None = None) -> None:
        self._dcs = dcs or []

    def get_by_id(self, dc_id: int) -> DistributionCenterDTO | None:
        return next((d for d in self._dcs if d.id == dc_id), None)

    def get_by_code(self, code: str) -> DistributionCenterDTO | None:
        return next((d for d in self._dcs if d.code == code), None)

    def get_active_source_dcs(self, exclude_dc_id: int) -> list[DistributionCenterDTO]:
        return [d for d in self._dcs if d.id != exclude_dc_id and d.is_active]


class FakeProductRepository:
    def __init__(self, products: list[ProductDTO] | None = None) -> None:
        self._products = products or []

    def get_by_id(self, product_id: int) -> ProductDTO | None:
        return next((p for p in self._products if p.id == product_id), None)

    def get_by_sku(self, sku: str) -> ProductDTO | None:
        return next((p for p in self._products if p.sku == sku), None)


class FakeInventoryRepository:
    def __init__(self, balances: list[InventoryBalanceDTO] | None = None) -> None:
        self._balances = balances or []

    def get_balance(self, dc_id: int, product_id: int) -> InventoryBalanceDTO | None:
        return next(
            (b for b in self._balances if b.dc_id == dc_id and b.product_id == product_id),
            None,
        )


class FakeInventoryPolicyRepository:
    def __init__(self, policies: list[InventoryPolicyDTO] | None = None) -> None:
        self._policies = policies or []

    def get_active_policy(self, dc_id: int, product_id: int) -> InventoryPolicyDTO | None:
        return next(
            (
                p
                for p in self._policies
                if p.dc_id == dc_id and p.product_id == product_id and p.is_active
            ),
            None,
        )


class FakeDemandRepository:
    def __init__(self) -> None:
        pass

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ):
        return []


class FakeRouteRepository:
    def __init__(self, routes: list[DCRouteDTO] | None = None) -> None:
        self.routes = routes or []

    def get_active_route(self, source_dc_id: int, target_dc_id: int) -> DCRouteDTO | None:
        return next(
            (
                r
                for r in self.routes
                if r.source_dc_id == source_dc_id and r.target_dc_id == target_dc_id and r.is_active
            ),
            None,
        )


class FakeTransferRecommendationRepository:
    def __init__(self) -> None:
        self.recommendations: list[TransferRecommendationDTO] = []
        self._next_id = 1

    def create_recommendation(
        self, create_data: TransferRecommendationCreateData
    ) -> TransferRecommendationDTO:
        dto = TransferRecommendationDTO(
            id=self._next_id,
            recommendation_code=create_data.recommendation_code,
            incident_id=create_data.incident_id,
            source_dc_id=create_data.source_dc_id,
            target_dc_id=create_data.target_dc_id,
            product_id=create_data.product_id,
            recommended_qty=create_data.recommended_qty,
            feasible_qty_snapshot=create_data.feasible_qty_snapshot,
            source_surplus_snapshot=create_data.source_surplus_snapshot,
            transit_days_snapshot=create_data.transit_days_snapshot,
            route_unit_cost_snapshot=create_data.route_unit_cost_snapshot,
            estimated_cost_snapshot=create_data.estimated_cost_snapshot,
            rationale=create_data.rationale,
            recommendation_source=create_data.recommendation_source,
            status=create_data.status,
            created_at=datetime(2026, 9, 16, 14, 0, 0),
        )
        self._next_id += 1
        self.recommendations.append(dto)
        return dto


class FakeAuditRepository:
    def __init__(self) -> None:
        self.audit_events: list[AuditEventDTO] = []
        self._next_id = 1

    def create_audit_event(self, audit_data: AuditEventCreateData) -> AuditEventDTO:
        dto = AuditEventDTO(
            id=self._next_id,
            incident_id=audit_data.incident_id,
            action=audit_data.action,
            recommendation_id=audit_data.recommendation_id,
            planner_id=audit_data.planner_id,
            input_snapshot_json=audit_data.input_snapshot_json,
            final_approved_qty=audit_data.final_approved_qty,
            created_at=datetime(2026, 9, 16, 14, 0, 0),
        )
        self._next_id += 1
        self.audit_events.append(dto)
        return dto


# --- Mock AI Providers ---


class SuccessfulMockAIProvider:
    """Mock AI Provider returning a valid candidate choice."""

    def __init__(self, selected_candidate_id: str = "CAND-DC-IND-DC-CHI") -> None:
        self.selected_candidate_id = selected_candidate_id
        self.captured_input: AIRecommendationInputDTO | None = None
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        self.captured_input = input_data
        return AIRecommendationOutputDTO(
            selected_candidate_id=self.selected_candidate_id,
            rationale="Selected Indianapolis due to lowest transit time and optimal total cost.",
        )


class TimeoutMockAIProvider:
    """Mock AI Provider raising a TimeoutError."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        raise TimeoutError("External AI recommendation provider timed out after 5.0 seconds")


class ExceptionMockAIProvider:
    """Mock AI Provider raising a generic RuntimeError."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        raise RuntimeError("External AI service connection error")


class MalformedOutputMockAIProvider:
    """Mock AI Provider returning malformed/empty response."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        return AIRecommendationOutputDTO(selected_candidate_id="", rationale="")


class UnknownCandidateMockAIProvider:
    """Mock AI Provider returning a candidate ID that does not exist."""

    def __init__(self) -> None:
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        return AIRecommendationOutputDTO(
            selected_candidate_id="CAND-DC-UNKNOWN-DC-CHI",
            rationale="Selected non-existent candidate ID",
        )


class TransactionCheckingMockAIProvider:
    """Mock AI Provider verifying zero open database transactions during execution."""

    def __init__(self, uow: FakeUnitOfWork) -> None:
        self.uow = uow
        self.call_count = 0

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.call_count += 1
        assert not self.uow.in_transaction, (
            "AI Provider call must NOT occur inside a DB transaction!"
        )
        return AIRecommendationOutputDTO(
            selected_candidate_id="CAND-DC-IND-DC-CHI",
            rationale="Verified zero DB transaction active during AI call.",
        )


# --- Helper Setup Function ---


def create_golden_scenario_components():
    """Sets up standard Golden Scenario components and repositories."""
    uow = FakeUnitOfWork()

    # DCs: Target = Chicago (1), Sources = Indianapolis (2), Dallas (3)
    dc_chi = DistributionCenterDTO(
        id=1, code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=True
    )
    dc_ind = DistributionCenterDTO(
        id=2, code="DC-IND", name="Indianapolis DC", city="Indianapolis", state="IN", is_active=True
    )
    dc_dal = DistributionCenterDTO(
        id=3, code="DC-DAL", name="Dallas DC", city="Dallas", state="TX", is_active=True
    )

    product = ProductDTO(
        id=10, sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )

    incident = RiskIncidentDTO(
        id=100,
        incident_code="INC-DC-CHI-SKU-8842-20260916",
        target_dc_id=1,
        product_id=10,
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="OPEN",
    )

    # Balances:
    # Indianapolis: On hand 650 -> available 650
    # Dallas: On hand 900 -> available 900
    ind_balance = InventoryBalanceDTO(
        id=20, dc_id=2, product_id=10, on_hand_qty=650, reserved_qty=0
    )
    dal_balance = InventoryBalanceDTO(
        id=30, dc_id=3, product_id=10, on_hand_qty=900, reserved_qty=0
    )

    # Policies:
    # Indianapolis: safety_stock_days=200 -> surplus = 650 - 200 = 450
    # Dallas: safety_stock_days=200 -> surplus = 900 - 200 = 700
    ind_policy = InventoryPolicyDTO(
        id=200, dc_id=2, product_id=10, safety_stock_days=200.0, is_active=True
    )
    dal_policy = InventoryPolicyDTO(
        id=300, dc_id=3, product_id=10, safety_stock_days=200.0, is_active=True
    )

    # Routes:
    # DC-IND -> DC-CHI: transit 1 day (< 2.5 DUS) -> FEASIBLE! (cost per unit 2.50)
    # DC-DAL -> DC-CHI: transit 3 days (>= 2.5 DUS) -> INFEASIBLE! (cost per unit 1.50)
    ind_route = DCRouteDTO(
        id=1000, source_dc_id=2, target_dc_id=1, transit_days=1, cost_per_unit=2.50, is_active=True
    )
    dal_route = DCRouteDTO(
        id=2000, source_dc_id=3, target_dc_id=1, transit_days=3, cost_per_unit=1.50, is_active=True
    )

    risk_repo = FakeRiskIncidentRepository([incident])
    dc_repo = FakeDistributionCenterRepository([dc_chi, dc_ind, dc_dal])
    product_repo = FakeProductRepository([product])
    inventory_repo = FakeInventoryRepository([ind_balance, dal_balance])
    policy_repo = FakeInventoryPolicyRepository([ind_policy, dal_policy])
    demand_repo = FakeDemandRepository()
    route_repo = FakeRouteRepository([ind_route, dal_route])
    rec_repo = FakeTransferRecommendationRepository()
    audit_repo = FakeAuditRepository()

    discovery_service = CandidateDiscoveryService(
        risk_repo=risk_repo,
        dc_repo=dc_repo,
        inventory_repo=inventory_repo,
        demand_repo=demand_repo,
        policy_repo=policy_repo,
        route_repo=route_repo,
    )

    return {
        "uow": uow,
        "risk_repo": risk_repo,
        "dc_repo": dc_repo,
        "product_repo": product_repo,
        "inventory_repo": inventory_repo,
        "policy_repo": policy_repo,
        "demand_repo": demand_repo,
        "route_repo": route_repo,
        "rec_repo": rec_repo,
        "audit_repo": audit_repo,
        "discovery_service": discovery_service,
    }


# --- Minimum 12 Required Test Matrix ---


def test_recommendation_success_ai() -> None:
    """1. Verify AI provider success path creates recommendation."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider(selected_candidate_id="CAND-DC-IND-DC-CHI")

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is True
    assert result.status == "PROPOSED"
    assert result.source_dc_code == "DC-IND"
    assert result.target_dc_code == "DC-CHI"
    assert result.product_sku == "SKU-8842"
    assert result.recommended_qty == 180
    assert result.estimated_total_cost == Decimal("450.0")
    assert result.recommendation_source == "AI"
    assert "Selected Indianapolis" in result.rationale

    # Verify persistence
    assert len(c["rec_repo"].recommendations) == 1
    assert len(c["audit_repo"].audit_events) == 1
    assert c["audit_repo"].audit_events[0].action == "RECOMMENDATION_GENERATED"
    assert c["uow"].committed is True


def test_recommendation_ai_timeout_fallback() -> None:
    """2. Verify AI timeout triggers deterministic fallback."""
    c = create_golden_scenario_components()
    ai_provider = TimeoutMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is True
    assert result.status == "PROPOSED"
    assert result.source_dc_code == "DC-IND"
    assert result.recommendation_source == "DETERMINISTIC_FALLBACK"
    assert "[DETERMINISTIC_FALLBACK]" in result.rationale
    assert len(c["rec_repo"].recommendations) == 1


def test_recommendation_ai_exception_fallback() -> None:
    """3. Verify AI exception triggers deterministic fallback."""
    c = create_golden_scenario_components()
    ai_provider = ExceptionMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is True
    assert result.recommendation_source == "DETERMINISTIC_FALLBACK"
    assert "[DETERMINISTIC_FALLBACK]" in result.rationale


def test_recommendation_malformed_json_fallback() -> None:
    """4. Verify malformed AI output triggers deterministic fallback."""
    c = create_golden_scenario_components()
    ai_provider = MalformedOutputMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is True
    assert result.recommendation_source == "DETERMINISTIC_FALLBACK"
    assert "[DETERMINISTIC_FALLBACK]" in result.rationale


def test_recommendation_unknown_candidate_id_fallback() -> None:
    """5. Verify unknown candidate ID returned by AI triggers deterministic fallback."""
    c = create_golden_scenario_components()
    ai_provider = UnknownCandidateMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is True
    assert result.recommendation_source == "DETERMINISTIC_FALLBACK"
    assert "[DETERMINISTIC_FALLBACK]" in result.rationale
    assert result.source_dc_code == "DC-IND"


def test_validation_failure_raises_exception_no_silent_fallback() -> None:
    """6. Verify post-validation failure raises RecommendationValidationError."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    # Deactivate source DC in repository to trigger post-validation guardrail failure
    c["dc_repo"]._dcs[1] = DistributionCenterDTO(
        id=2,
        code="DC-IND",
        name="Indianapolis DC",
        city="Indianapolis",
        state="IN",
        is_active=False,
    )

    # Mock discovery service to return candidate discovered before DC state change
    candidate = PreValidatedCandidate(
        candidate_id="CAND-DC-IND-DC-CHI",
        source_dc_code="DC-IND",
        available_surplus=450,
        feasible_quantity=180,
        transit_days=1,
        route_unit_cost=2.50,
        estimated_total_cost=450.00,
        can_arrive_before_stockout=True,
    )

    from app.services.dtos import CandidateDiscoveryResultDTO

    c["discovery_service"].discover_feasible_candidates = lambda inc_id: (
        CandidateDiscoveryResultDTO(
            incident_id=100,
            incident_code="INC-DC-CHI-SKU-8842-20260916",
            target_dc_id=1,
            target_dc_code="DC-CHI",
            product_id=10,
            target_shortage_qty=180,
            days_to_stockout=2.5,
            feasible_candidates=[candidate],
        )
    )

    with pytest.raises(RecommendationValidationError) as exc_info:
        service.generate_recommendation(100)

    assert "Source DC 'DC-IND' is inactive" in str(exc_info.value)
    # Ensure NO recommendation was created and NO commit executed
    assert len(c["rec_repo"].recommendations) == 0


def test_recommendation_no_candidates_explicit_outcome() -> None:
    """7. Verify zero feasible candidates returns NO_FEASIBLE_SOURCE without calling AI provider."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    # Set transit days of Indianapolis route to 5 (>= 2.5 DUS), making all sources infeasible
    c["route_repo"].routes[0] = DCRouteDTO(
        id=1000, source_dc_id=2, target_dc_id=1, transit_days=5, cost_per_unit=2.50, is_active=True
    )

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    assert result.has_recommendation is False
    assert result.status == "NO_FEASIBLE_SOURCE"
    assert ai_provider.call_count == 0
    assert len(c["rec_repo"].recommendations) == 0
    assert len(c["audit_repo"].audit_events) == 1
    assert c["audit_repo"].audit_events[0].action == "NO_FEASIBLE_SOURCE_FOUND"


def test_ai_input_dto_contains_no_internal_db_ids() -> None:
    """8. Verify AI input DTO contains only business identifiers and zero DB surrogate IDs."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    service.generate_recommendation(100)

    ai_input = ai_provider.captured_input
    assert ai_input is not None
    assert ai_input.incident_code == "INC-DC-CHI-SKU-8842-20260916"
    assert ai_input.target_dc_code == "DC-CHI"
    assert ai_input.product_sku == "SKU-8842"
    assert ai_input.product_name == "Salmon Fillets"
    assert ai_input.category == "Seafood"
    assert ai_input.days_to_stockout == 2.5
    assert ai_input.shortage_qty == 180
    assert ai_input.severity == "CRITICAL"

    # Verify absence of DB surrogate IDs
    assert not hasattr(ai_input, "incident_id")
    assert not hasattr(ai_input, "target_dc_id")
    assert not hasattr(ai_input, "product_id")


def test_no_db_transaction_during_ai_call() -> None:
    """9. Verify AI provider call occurs outside any active database transaction."""
    c = create_golden_scenario_components()
    ai_provider = TransactionCheckingMockAIProvider(c["uow"])

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)
    assert result.has_recommendation is True
    assert ai_provider.call_count == 1


def test_candidate_id_mapping() -> None:
    """10. Verify candidate ID maps correctly to PreValidatedCandidate."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider(selected_candidate_id="CAND-DC-IND-DC-CHI")

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)
    assert result.source_dc_code == "DC-IND"
    assert result.target_dc_code == "DC-CHI"


def test_recommendation_snapshots_correctness() -> None:
    """11. Verify persisted snapshot fields match selected candidate snapshot exactly."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    service.generate_recommendation(100)

    saved_rec = c["rec_repo"].recommendations[0]
    assert saved_rec.feasible_qty_snapshot == 180
    assert saved_rec.source_surplus_snapshot == 450
    assert saved_rec.transit_days_snapshot == 1
    assert saved_rec.route_unit_cost_snapshot == Decimal("2.5")
    assert saved_rec.estimated_cost_snapshot == Decimal("450.0")


def test_recommendation_golden_scenario_e2e() -> None:
    """12. Verify Golden Scenario E2E: Dallas excluded, Indianapolis recommended."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    result = service.generate_recommendation(100)

    # Dallas must NOT be in AI input candidates
    candidate_codes = [
        cand.source_dc_code for cand in ai_provider.captured_input.prevalidated_candidates
    ]
    assert "DC-DAL" not in candidate_codes
    assert "DC-IND" in candidate_codes

    # Golden recommendation verification
    assert result.has_recommendation is True
    assert result.status == "PROPOSED"
    assert result.source_dc_code == "DC-IND"
    assert result.target_dc_code == "DC-CHI"
    assert result.recommended_qty == 180
    assert result.estimated_total_cost == Decimal("450.0")
    assert result.recommendation_source == "AI"


# --- Additional Boundary & Error Tests ---


def test_recommendation_incident_not_found_raises_exception() -> None:
    """Verify non-existent incident raises ResourceNotFoundError."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.generate_recommendation(999)

    assert "RiskIncident '999' not found" in str(exc_info.value)


def test_recommendation_incident_not_open_raises_exception() -> None:
    """Verify non-OPEN incident status raises ResourceInactiveError."""
    c = create_golden_scenario_components()
    ai_provider = SuccessfulMockAIProvider()

    c["risk_repo"]._incidents[0] = RiskIncidentDTO(
        id=100,
        incident_code="INC-CLOSED",
        target_dc_id=1,
        product_id=10,
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="RESOLVED",
    )

    service = RecommendationService(
        risk_repo=c["risk_repo"],
        dc_repo=c["dc_repo"],
        product_repo=c["product_repo"],
        inventory_repo=c["inventory_repo"],
        policy_repo=c["policy_repo"],
        route_repo=c["route_repo"],
        recommendation_repo=c["rec_repo"],
        audit_repo=c["audit_repo"],
        candidate_discovery_service=c["discovery_service"],
        ai_provider=ai_provider,
        uow=c["uow"],
        demand_repo=c["demand_repo"],
    )

    with pytest.raises(ResourceInactiveError) as exc_info:
        service.generate_recommendation(100)

    assert "only OPEN incidents are eligible" in str(exc_info.value)
