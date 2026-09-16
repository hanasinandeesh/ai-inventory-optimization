"""
Test Seed E2E Integration.
Executes the full application workflow against seeded database data.
Proves application is data-driven and resolves Golden Scenario through database queries.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyProductRepository,
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyRouteRepository,
)
from app.infrastructure.db.seed.seed import seed_database
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.process_risk_detection_service import ProcessRiskDetectionService


def test_seed_e2e_golden_scenario_workflow(test_db: Session) -> None:
    """
    Executes E2E integration test:
    1. Seeds database with synthetic data (including Golden Scenario).
    2. Runs ProcessRiskDetectionService for DC-CHI and SKU-8842 on 2026-09-16.
    3. Verifies RiskIncident creation with DUS=2.5, shortage=180, severity=CRITICAL.
    4. Runs CandidateDiscoveryService for the created RiskIncident.
    5. Verifies DC-IND is returned as feasible candidate with qty=180, cost=450.
    6. Verifies DC-DAL is excluded (transit=3 >= DUS=2.5).
    """
    # 1. Seed database
    seed_database(test_db, reset=True)

    # 2. Instantiate concrete repositories & services using test_db session
    dc_repo = SQLAlchemyDistributionCenterRepository(test_db)
    product_repo = SQLAlchemyProductRepository(test_db)
    inventory_repo = SQLAlchemyInventoryRepository(test_db)
    demand_repo = SQLAlchemyDemandRepository(test_db)
    policy_repo = SQLAlchemyInventoryPolicyRepository(test_db)
    risk_repo = SQLAlchemyRiskIncidentRepository(test_db)
    audit_repo = SQLAlchemyAuditRepository(test_db)
    route_repo = SQLAlchemyRouteRepository(test_db)
    uow = SQLAlchemyUnitOfWork(test_db)

    risk_service = ProcessRiskDetectionService(
        dc_repo=dc_repo,
        product_repo=product_repo,
        inventory_repo=inventory_repo,
        demand_repo=demand_repo,
        policy_repo=policy_repo,
        risk_repo=risk_repo,
        audit_repo=audit_repo,
        uow=uow,
    )

    candidate_service = CandidateDiscoveryService(
        risk_repo=risk_repo,
        dc_repo=dc_repo,
        inventory_repo=inventory_repo,
        demand_repo=demand_repo,
        policy_repo=policy_repo,
        route_repo=route_repo,
    )

    # 3. Execute ProcessRiskDetectionService for Golden Scenario
    detection_date = date(2026, 9, 16)
    risk_result = risk_service.process_risk_detection(
        target_dc_id_or_code="DC-CHI",
        product_id_or_sku="SKU-8842",
        detection_date=detection_date,
    )

    # Verify Risk Detection results
    assert risk_result.days_to_stockout == 2.5
    assert risk_result.shortage_quantity == 180
    assert risk_result.severity == "CRITICAL"
    assert risk_result.target_dc_code == "DC-CHI"
    assert risk_result.product_sku == "SKU-8842"

    # 4. Execute CandidateDiscoveryService for the resulting RiskIncident
    candidate_result = candidate_service.discover_feasible_candidates(
        incident_id_or_code=risk_result.incident_id
    )

    # 5. Verify Feasible Candidates
    assert len(candidate_result.feasible_candidates) == 1
    candidate = candidate_result.feasible_candidates[0]

    assert candidate.source_dc_code == "DC-IND"
    assert candidate.feasible_quantity == 180
    assert candidate.transit_days == 1
    assert candidate.route_unit_cost == Decimal("2.50")
    assert candidate.estimated_total_cost == Decimal("450.00")
    assert candidate.can_arrive_before_stockout is True

    # 6. Verify DC-DAL was excluded from feasible candidates (transit=3 >= DUS=2.5)
    source_codes = [c.source_dc_code for c in candidate_result.feasible_candidates]
    assert "DC-DAL" not in source_codes
