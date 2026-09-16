from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.models.supplier import Supplier
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyRouteRepository,
    SQLAlchemyTransferRecommendationRepository,
)
from app.services.dtos import AuditEventDTO


@pytest.fixture(scope="function")
def seeded_data(test_db: Session) -> dict[str, int]:
    """Populates basic master data (Product, DCs, Supplier) for repository testing."""
    product = Product(
        sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )
    supplier = Supplier(supplier_code="SUP-001", name="Atlantic Seafood")
    dc_chi = DistributionCenter(
        code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=True
    )
    dc_ind = DistributionCenter(
        code="DC-IND", name="Indianapolis DC", city="Indianapolis", state="IN", is_active=True
    )
    dc_inact = DistributionCenter(
        code="DC-INACT", name="Inactive DC", city="Inactive", state="XX", is_active=False
    )

    test_db.add_all([product, supplier, dc_chi, dc_ind, dc_inact])
    test_db.commit()

    return {
        "product_id": product.id,
        "supplier_id": supplier.id,
        "chi_dc_id": dc_chi.id,
        "ind_dc_id": dc_ind.id,
        "inact_dc_id": dc_inact.id,
    }


def test_inventory_repository_lookup(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify InventoryRepository retrieves inventory balance without auto-committing."""
    balance = InventoryBalance(
        dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        on_hand_qty=100,
        reserved_qty=10,
    )
    test_db.add(balance)
    test_db.commit()

    repo = SQLAlchemyInventoryRepository(test_db)
    fetched = repo.get_balance(seeded_data["chi_dc_id"], seeded_data["product_id"])

    assert fetched is not None
    assert fetched.on_hand_qty == 100
    assert fetched.reserved_qty == 10

    # Ensure repository does not contain mutation methods
    assert not hasattr(repo, "update_balance")
    assert not hasattr(repo, "transfer_inventory")


def test_demand_repository_signal_retrieval(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify DemandRepository retrieves signals within a date range ordered by date."""
    d1 = DailyDemandSignal(
        dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        signal_date=date(2026, 9, 15),
        daily_demand_qty=35,
    )
    d2 = DailyDemandSignal(
        dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        signal_date=date(2026, 9, 16),
        daily_demand_qty=40,
    )
    test_db.add_all([d1, d2])
    test_db.commit()

    repo = SQLAlchemyDemandRepository(test_db)
    signals = repo.get_daily_demand_signals(
        dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        start_date=date(2026, 9, 15),
        end_date=date(2026, 9, 16),
    )

    assert len(signals) == 2
    assert signals[0].signal_date == date(2026, 9, 15)
    assert signals[1].signal_date == date(2026, 9, 16)


def test_inventory_policy_repository(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify InventoryPolicyRepository retrieves active policy."""
    policy = InventoryPolicy(
        dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        safety_stock_days=7.0,
        is_active=True,
    )
    test_db.add(policy)
    test_db.commit()

    repo = SQLAlchemyInventoryPolicyRepository(test_db)
    fetched = repo.get_active_policy(seeded_data["chi_dc_id"], seeded_data["product_id"])

    assert fetched is not None
    assert fetched.safety_stock_days == 7.0


def test_distribution_center_repository(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify DistributionCenterRepository lookups and active source DC discovery."""
    repo = SQLAlchemyDistributionCenterRepository(test_db)

    dc = repo.get_by_code("DC-CHI")
    assert dc is not None
    assert dc.id == seeded_data["chi_dc_id"]

    active_sources = repo.get_active_source_dcs(exclude_dc_id=seeded_data["chi_dc_id"])
    assert len(active_sources) == 1
    assert active_sources[0].code == "DC-IND"


def test_route_repository(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify RouteRepository lookup for active routes and exclusion of inactive routes."""
    active_route = DCRoute(
        source_dc_id=seeded_data["ind_dc_id"],
        target_dc_id=seeded_data["chi_dc_id"],
        transit_days=1,
        cost_per_unit=Decimal("2.50"),
        is_active=True,
    )
    inactive_route = DCRoute(
        source_dc_id=seeded_data["inact_dc_id"],
        target_dc_id=seeded_data["chi_dc_id"],
        transit_days=3,
        cost_per_unit=Decimal("5.00"),
        is_active=False,
    )
    test_db.add_all([active_route, inactive_route])
    test_db.commit()

    repo = SQLAlchemyRouteRepository(test_db)

    fetched_active = repo.get_active_route(
        source_dc_id=seeded_data["ind_dc_id"], target_dc_id=seeded_data["chi_dc_id"]
    )
    assert fetched_active is not None
    assert fetched_active.transit_days == 1

    fetched_inactive = repo.get_active_route(
        source_dc_id=seeded_data["inact_dc_id"], target_dc_id=seeded_data["chi_dc_id"]
    )
    assert fetched_inactive is None


def test_risk_incident_repository(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify RiskIncident creation, lookup by code/id, and idempotent finding."""
    repo = SQLAlchemyRiskIncidentRepository(test_db)

    incident = RiskIncident(
        incident_code="INC-20260916-001",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="OPEN",
    )
    created = repo.create_incident(incident)
    assert created.id is not None

    # Verify existing incident lookup for idempotency
    existing = repo.find_existing_incident(
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        status="OPEN",
    )
    assert existing is not None
    assert existing.incident_code == "INC-20260916-001"

    # Status update
    updated = repo.update_status(incident.id, "RESOLVED")
    assert updated is True
    assert repo.get_by_id(incident.id).status == "RESOLVED"


def test_recommendation_repository_and_conditional_update(
    test_db: Session, seeded_data: dict[str, int]
) -> None:
    """
    Verify TransferRecommendation creation, retrieval, and conditional
    decision status transitions.
    """
    incident = RiskIncident(
        incident_code="INC-REC-TEST-001",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="OPEN",
    )
    test_db.add(incident)
    test_db.commit()

    rec = TransferRecommendation(
        recommendation_code="REC-20260916-001",
        incident_id=incident.id,
        source_dc_id=seeded_data["ind_dc_id"],
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        recommended_qty=180,
        feasible_qty_snapshot=180,
        source_surplus_snapshot=450,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("2.50"),
        estimated_cost_snapshot=Decimal("450.00"),
        rationale="Feasible source DC",
        recommendation_source="AI",
        status="PROPOSED",
    )

    repo = SQLAlchemyTransferRecommendationRepository(test_db)
    created = repo.create_recommendation(rec)
    assert created.id is not None

    # 1. Conditional approval on valid PROPOSED state -> 1 row affected
    rows_affected = repo.update_decision_status(created.id, "APPROVED")
    assert rows_affected == 1

    # Verify status changed to APPROVED
    assert repo.get_by_id(created.id).status == "APPROVED"

    # 2. Duplicate approval on already APPROVED state -> 0 rows affected (terminal state protection)
    conflict_rows = repo.update_decision_status(created.id, "REJECTED")
    assert conflict_rows == 0
    assert repo.get_by_id(created.id).status == "APPROVED"


def test_audit_repository_append_only(test_db: Session, seeded_data: dict[str, int]) -> None:
    """Verify AuditRepository append-only creation and retrieval with no mutation methods."""
    incident = RiskIncident(
        incident_code="INC-AUDIT-TEST",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="CRITICAL",
    )
    test_db.add(incident)
    test_db.commit()

    repo = SQLAlchemyAuditRepository(test_db)

    # Verify NO update or delete methods exist on AuditRepository
    assert not hasattr(repo, "update_audit")
    assert not hasattr(repo, "delete_audit")
    assert not hasattr(repo, "update_audit_event")
    assert not hasattr(repo, "delete_audit_event")

    audit = AuditEvent(
        incident_id=incident.id,
        recommendation_id=None,
        planner_id=None,
        action="RISK_DETECTED",
        input_snapshot_json='{"shortage": 50}',
    )
    created = repo.create_audit_event(audit)
    assert created.id is not None

    events = repo.get_by_incident_id(incident.id)
    assert len(events) == 1
    assert isinstance(events[0], AuditEventDTO)
    assert events[0].action == "RISK_DETECTED"


def test_audit_repository_dto_mapping_and_ordering(
    test_db: Session, seeded_data: dict[str, int]
) -> None:
    """Verify SQLAlchemyAuditRepository returns AuditEventDTO objects with incident filtering
    and oldest-first ordering."""
    from datetime import UTC, datetime, timedelta

    from app.services.dtos import AuditEventDTO

    incident1 = RiskIncident(
        incident_code="INC-AUDIT-DTO-1",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="CRITICAL",
    )
    incident2 = RiskIncident(
        incident_code="INC-AUDIT-DTO-2",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=2.0,
        days_to_stockout=2.0,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=100.0,
        severity="HIGH",
    )
    test_db.add_all([incident1, incident2])
    test_db.commit()

    repo = SQLAlchemyAuditRepository(test_db)
    now = datetime.now(UTC)

    # 1. First event: System event with None for nullable fields
    e1 = AuditEvent(
        incident_id=incident1.id,
        action="RISK_DETECTED",
        recommendation_id=None,
        planner_id=None,
        input_snapshot_json=None,
        final_approved_qty=None,
        created_at=now - timedelta(minutes=10),
    )
    test_db.add(e1)

    # 2. Second event: Recommendation generation
    e2 = AuditEvent(
        incident_id=incident1.id,
        action="RECOMMENDATION_GENERATED",
        recommendation_id=10,
        planner_id=None,
        input_snapshot_json='{"rec": 10}',
        final_approved_qty=None,
        created_at=now - timedelta(minutes=5),
    )
    test_db.add(e2)

    # 3. Third event: Planner approval with non-null values
    e3 = AuditEvent(
        incident_id=incident1.id,
        action="PLANNER_APPROVED",
        recommendation_id=10,
        planner_id="planner_john",
        input_snapshot_json='{"comment": "Approved"}',
        final_approved_qty=180,
        created_at=now,
    )
    test_db.add(e3)

    # 4. Unrelated event for incident2
    e_other = AuditEvent(
        incident_id=incident2.id,
        action="RISK_DETECTED",
        recommendation_id=None,
        planner_id=None,
        input_snapshot_json=None,
        final_approved_qty=None,
        created_at=now,
    )
    test_db.add(e_other)
    test_db.commit()

    # Query audit events for incident1
    results = repo.get_by_incident_id(incident1.id)

    # 1. Check count and incident_id filtering (incident2 excluded)
    assert len(results) == 3
    assert all(r.incident_id == incident1.id for r in results)

    # 2. Check return type: all items are AuditEventDTO instances
    assert all(isinstance(r, AuditEventDTO) for r in results)

    # 3. Check ordering: oldest first (e1 -> e2 -> e3)
    assert results[0].action == "RISK_DETECTED"
    assert results[1].action == "RECOMMENDATION_GENERATED"
    assert results[2].action == "PLANNER_APPROVED"
    assert results[0].created_at <= results[1].created_at <= results[2].created_at

    # 4. Check nullable fields on e1 (all nullable fields None)
    assert results[0].recommendation_id is None
    assert results[0].planner_id is None
    assert results[0].input_snapshot_json is None
    assert results[0].final_approved_qty is None

    # 5. Check populated fields on e3
    assert results[2].recommendation_id == 10
    assert results[2].planner_id == "planner_john"
    assert results[2].input_snapshot_json == '{"comment": "Approved"}'
    assert results[2].final_approved_qty == 180
    assert results[2].created_at is not None


def test_repository_methods_do_not_commit_transactions(
    test_db: Session, seeded_data: dict[str, int]
) -> None:
    """Verify repository operations add/flush to session without performing session.commit()."""
    repo = SQLAlchemyRiskIncidentRepository(test_db)

    incident = RiskIncident(
        incident_code="INC-NO-COMMIT-TEST",
        target_dc_id=seeded_data["chi_dc_id"],
        product_id=seeded_data["product_id"],
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="CRITICAL",
    )
    repo.create_incident(incident)

    # Rollback transaction
    test_db.rollback()

    # Verify record was rolled back because repository did NOT call session.commit()
    fetched = test_db.execute(
        select(RiskIncident).where(RiskIncident.incident_code == "INC-NO-COMMIT-TEST")
    ).scalar_one_or_none()
    assert fetched is None
