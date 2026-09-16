"""
Tests for CandidateDiscoveryService.
Verifies candidate source DC discovery, deterministic arrival feasibility rules,
Golden Scenario filtering (Indianapolis included, Dallas excluded), and error handling.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyRouteRepository,
)
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.dtos import (
    DCRouteDTO,
    DistributionCenterDTO,
    InventoryBalanceDTO,
    InventoryPolicyDTO,
    ProductDTO,
    RiskIncidentDTO,
)
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from tests.services.test_process_risk_detection_service import (
    FakeDemandRepository,
    FakeDistributionCenterRepository,
    FakeInventoryPolicyRepository,
    FakeInventoryRepository,
    FakeRiskIncidentRepository,
)


class FakeRouteRepository:
    def __init__(self, routes: list[DCRouteDTO] | None = None) -> None:
        self._routes = routes or []

    def get_active_route(self, source_dc_id: int, target_dc_id: int) -> DCRouteDTO | None:
        return next(
            (
                r
                for r in self._routes
                if r.source_dc_id == source_dc_id and r.target_dc_id == target_dc_id and r.is_active
            ),
            None,
        )


def make_golden_candidate_setup():
    """Sets up Golden Scenario test data for candidate discovery."""
    # Target: Chicago DC (ID 1)
    dc_chi = DistributionCenterDTO(
        id=1, code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=True
    )

    # Candidate 1: Indianapolis DC (ID 2) - FEASIBLE (Transit 1 day < 2.5 DUS)
    dc_ind = DistributionCenterDTO(
        id=2,
        code="DC-IND",
        name="Indianapolis DC",
        city="Indianapolis",
        state="IN",
        is_active=True,
    )

    # Candidate 2: Dallas DC (ID 3) - INFEASIBLE (Transit 3 days >= 2.5 DUS)
    dc_dal = DistributionCenterDTO(
        id=3, code="DC-DAL", name="Dallas DC", city="Dallas", state="TX", is_active=True
    )

    product = ProductDTO(
        id=10, sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )

    # Risk Incident for Chicago DC: Shortage = 180, DUS = 2.5 days
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

    # Candidate Balances & Policies
    # Indianapolis: Available 650, Safety Stock 200 -> Surplus = 450
    bal_ind = InventoryBalanceDTO(id=20, dc_id=2, product_id=10, on_hand_qty=650, reserved_qty=0)
    pol_ind = InventoryPolicyDTO(
        id=200, dc_id=2, product_id=10, safety_stock_days=200.0, is_active=True
    )

    # Dallas: Available 900, Safety Stock 200 -> Surplus = 700
    bal_dal = InventoryBalanceDTO(id=30, dc_id=3, product_id=10, on_hand_qty=900, reserved_qty=0)
    pol_dal = InventoryPolicyDTO(
        id=300, dc_id=3, product_id=10, safety_stock_days=200.0, is_active=True
    )

    # Routes to Chicago
    route_ind = DCRouteDTO(
        id=50, source_dc_id=2, target_dc_id=1, transit_days=1, cost_per_unit=2.50, is_active=True
    )
    route_dal = DCRouteDTO(
        id=60, source_dc_id=3, target_dc_id=1, transit_days=3, cost_per_unit=4.00, is_active=True
    )

    return (
        incident,
        [dc_chi, dc_ind, dc_dal],
        product,
        [bal_ind, bal_dal],
        [pol_ind, pol_dal],
        [route_ind, route_dal],
    )


def test_golden_scenario_candidate_discovery():
    """Golden Scenario: Indianapolis is included, Dallas is excluded."""
    incident, dcs, product, balances, policies, routes = make_golden_candidate_setup()

    risk_repo = FakeRiskIncidentRepository()
    risk_repo.incidents.append(incident)

    dc_repo = FakeDistributionCenterRepository(dcs)
    inv_repo = FakeInventoryRepository(balances)
    demand_repo = FakeDemandRepository([])
    policy_repo = FakeInventoryPolicyRepository(policies)
    route_repo = FakeRouteRepository(routes)

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    result = service.discover_feasible_candidates(incident.id)

    assert result.incident_id == incident.id
    assert result.target_shortage_qty == 180
    assert result.days_to_stockout == 2.5

    # ONLY Indianapolis must be returned
    candidates = result.feasible_candidates
    assert len(candidates) == 1

    ind_cand = candidates[0]
    assert ind_cand.source_dc_code == "DC-IND"
    assert ind_cand.available_surplus == 450
    assert ind_cand.feasible_quantity == 180
    assert ind_cand.transit_days == 1
    assert ind_cand.route_unit_cost == 2.50
    assert ind_cand.estimated_total_cost == 450.00  # 180 * 2.50
    assert ind_cand.can_arrive_before_stockout is True


def test_missing_risk_incident():
    """Raises ResourceNotFoundError if incident does not exist."""
    _, dcs, product, balances, policies, routes = make_golden_candidate_setup()

    risk_repo = FakeRiskIncidentRepository()
    dc_repo = FakeDistributionCenterRepository(dcs)
    inv_repo = FakeInventoryRepository(balances)
    demand_repo = FakeDemandRepository([])
    policy_repo = FakeInventoryPolicyRepository(policies)
    route_repo = FakeRouteRepository(routes)

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.discover_feasible_candidates(999)

    assert "RiskIncident '999' not found" in str(exc_info.value)


def test_incident_not_open():
    """Raises ResourceInactiveError if incident status is RESOLVED or CLOSED."""
    incident, dcs, product, balances, policies, routes = make_golden_candidate_setup()

    resolved_incident = RiskIncidentDTO(
        id=incident.id,
        incident_code=incident.incident_code,
        target_dc_id=incident.target_dc_id,
        product_id=incident.product_id,
        current_dos=incident.current_dos,
        days_to_stockout=incident.days_to_stockout,
        projected_stockout_date=incident.projected_stockout_date,
        shortage_qty=incident.shortage_qty,
        severity=incident.severity,
        status="RESOLVED",
    )

    risk_repo = FakeRiskIncidentRepository()
    risk_repo.incidents.append(resolved_incident)

    dc_repo = FakeDistributionCenterRepository(dcs)
    inv_repo = FakeInventoryRepository(balances)
    demand_repo = FakeDemandRepository([])
    policy_repo = FakeInventoryPolicyRepository(policies)
    route_repo = FakeRouteRepository(routes)

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    with pytest.raises(ResourceInactiveError) as exc_info:
        service.discover_feasible_candidates(resolved_incident.id)

    assert "only OPEN incidents are eligible" in str(exc_info.value)


def test_inactive_route_excluded():
    """Candidate source with inactive transportation route is excluded."""
    incident, dcs, product, balances, policies, _ = make_golden_candidate_setup()

    # Route from Indianapolis is inactive
    inactive_route = DCRouteDTO(
        id=50, source_dc_id=2, target_dc_id=1, transit_days=1, cost_per_unit=2.50, is_active=False
    )

    risk_repo = FakeRiskIncidentRepository()
    risk_repo.incidents.append(incident)

    dc_repo = FakeDistributionCenterRepository(dcs)
    inv_repo = FakeInventoryRepository(balances)
    demand_repo = FakeDemandRepository([])
    policy_repo = FakeInventoryPolicyRepository(policies)
    route_repo = FakeRouteRepository([inactive_route])

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    result = service.discover_feasible_candidates(incident.id)
    assert len(result.feasible_candidates) == 0


def test_zero_surplus_excluded():
    """Candidate source with zero surplus (available <= safety stock) is excluded."""
    incident, dcs, product, _, policies, routes = make_golden_candidate_setup()

    # Indianapolis Available = 200, Safety Stock = 200 -> Surplus = 0
    bal_zero = InventoryBalanceDTO(id=20, dc_id=2, product_id=10, on_hand_qty=200, reserved_qty=0)

    risk_repo = FakeRiskIncidentRepository()
    risk_repo.incidents.append(incident)

    dc_repo = FakeDistributionCenterRepository(dcs)
    inv_repo = FakeInventoryRepository([bal_zero])
    demand_repo = FakeDemandRepository([])
    policy_repo = FakeInventoryPolicyRepository(policies)
    route_repo = FakeRouteRepository(routes)

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    result = service.discover_feasible_candidates(incident.id)
    assert len(result.feasible_candidates) == 0


def test_no_prohibited_imports_in_candidate_service():
    """Verify CandidateDiscoveryService module contains zero prohibited framework imports."""
    import inspect

    import app.services.candidate_discovery_service as service_module

    mod_dict = service_module.__dict__
    prohibited = ["sqlalchemy", "fastapi", "pydantic", "app.infrastructure"]

    for item in prohibited:
        assert item not in mod_dict, f"Service module imports prohibited package '{item}'"

    source = inspect.getsource(service_module)
    assert "app.infrastructure" not in source


def test_sqlalchemy_candidate_discovery_integration(test_db: Session):
    """Integration test verifying CandidateDiscoveryService with real SQLite DB."""
    dc_chi = DistributionCenter(
        code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=True
    )
    dc_ind = DistributionCenter(
        code="DC-IND", name="Indianapolis DC", city="Indianapolis", state="IN", is_active=True
    )
    dc_dal = DistributionCenter(
        code="DC-DAL", name="Dallas DC", city="Dallas", state="TX", is_active=True
    )
    product = Product(
        sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )
    test_db.add_all([dc_chi, dc_ind, dc_dal, product])
    test_db.commit()

    incident = RiskIncident(
        incident_code="INC-INTEG-001",
        target_dc_id=dc_chi.id,
        product_id=product.id,
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="OPEN",
    )
    test_db.add(incident)
    test_db.commit()

    # Balances
    bal_ind = InventoryBalance(
        dc_id=dc_ind.id, product_id=product.id, on_hand_qty=650, reserved_qty=0
    )
    bal_dal = InventoryBalance(
        dc_id=dc_dal.id, product_id=product.id, on_hand_qty=900, reserved_qty=0
    )

    # Policies
    pol_ind = InventoryPolicy(
        dc_id=dc_ind.id, product_id=product.id, safety_stock_days=200.0, is_active=True
    )
    pol_dal = InventoryPolicy(
        dc_id=dc_dal.id, product_id=product.id, safety_stock_days=200.0, is_active=True
    )

    # Routes
    route_ind = DCRoute(
        source_dc_id=dc_ind.id,
        target_dc_id=dc_chi.id,
        transit_days=1,
        cost_per_unit=Decimal("2.50"),
        is_active=True,
    )
    route_dal = DCRoute(
        source_dc_id=dc_dal.id,
        target_dc_id=dc_chi.id,
        transit_days=3,
        cost_per_unit=Decimal("4.00"),
        is_active=True,
    )

    test_db.add_all([bal_ind, bal_dal, pol_ind, pol_dal, route_ind, route_dal])
    test_db.commit()

    # Wire real repositories
    risk_repo = SQLAlchemyRiskIncidentRepository(test_db)
    dc_repo = SQLAlchemyDistributionCenterRepository(test_db)
    inv_repo = SQLAlchemyInventoryRepository(test_db)
    demand_repo = SQLAlchemyDemandRepository(test_db)
    policy_repo = SQLAlchemyInventoryPolicyRepository(test_db)
    route_repo = SQLAlchemyRouteRepository(test_db)

    service = CandidateDiscoveryService(
        risk_repo, dc_repo, inv_repo, demand_repo, policy_repo, route_repo
    )

    result = service.discover_feasible_candidates(incident.id)

    assert result.incident_id == incident.id
    assert len(result.feasible_candidates) == 1
    assert result.feasible_candidates[0].source_dc_code == "DC-IND"
    assert result.feasible_candidates[0].transit_days == 1
    assert result.feasible_candidates[0].feasible_quantity == 180
