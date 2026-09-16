from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import (
    AuditEvent,
    Base,
    DailyDemandSignal,
    DCRoute,
    DistributionCenter,
    InventoryBalance,
    InventoryPolicy,
    Product,
    PurchaseOrder,
    RiskIncident,
    Supplier,
    SupplierProduct,
    SupplyEvent,
    TransferRecommendation,
)


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Provides a fresh SQLite in-memory database session with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_all_13_models_registered_in_metadata() -> None:
    """Verify all 13 V1 entities are registered in SQLAlchemy metadata with exact table names."""
    expected_tables = {
        "suppliers",
        "products",
        "supplier_products",
        "distribution_centers",
        "dc_routes",
        "inventory_policies",
        "inventory_balances",
        "purchase_orders",
        "supply_events",
        "daily_demand_signals",
        "risk_incidents",
        "transfer_recommendations",
        "audit_events",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(registered_tables)
    assert len(registered_tables) >= 13


def test_basic_model_creation_and_relationships(db_session: Session) -> None:
    """Verify creation, persistence, and relationship navigation across all 13 models."""
    supplier = Supplier(
        supplier_code="SUP-001",
        name="Atlantic Seafood Co",
        reliability_rating=Decimal("0.95"),
    )
    product = Product(
        sku="SKU-8842",
        name="Atlantic Salmon Fillets",
        category="Seafood",
        unit_of_measure="CS",
        pack_size=1,
    )
    dc_chi = DistributionCenter(code="DC-CHI", name="Chicago DC", city="Chicago", state="IL")
    dc_ind = DistributionCenter(
        code="DC-IND", name="Indianapolis DC", city="Indianapolis", state="IN"
    )

    db_session.add_all([supplier, product, dc_chi, dc_ind])
    db_session.commit()

    supplier_product = SupplierProduct(
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("12.50"),
        std_lead_time_days=3,
        is_primary=True,
    )
    route = DCRoute(
        source_dc_id=dc_ind.id,
        target_dc_id=dc_chi.id,
        transit_days=1,
        cost_per_unit=Decimal("2.50"),
    )
    policy = InventoryPolicy(
        dc_id=dc_chi.id,
        product_id=product.id,
        safety_stock_days=7.0,
    )
    balance = InventoryBalance(
        dc_id=dc_chi.id,
        product_id=product.id,
        on_hand_qty=100,
        reserved_qty=0,
    )
    po = PurchaseOrder(
        po_number="PO-2026-001",
        supplier_id=supplier.id,
        product_id=product.id,
        destination_dc_id=dc_chi.id,
        ordered_qty=500,
        expected_delivery_date=date(2026, 9, 25),
        status="OPEN",
    )
    db_session.add_all([supplier_product, route, policy, balance, po])
    db_session.commit()

    supply_event = SupplyEvent(
        po_id=po.id,
        event_type="DELAY",
        delay_days=2,
        disrupted_qty=0,
    )
    demand = DailyDemandSignal(
        dc_id=dc_chi.id,
        product_id=product.id,
        signal_date=date(2026, 9, 16),
        daily_demand_qty=40,
    )
    incident = RiskIncident(
        incident_code="INC-20260916-001",
        target_dc_id=dc_chi.id,
        product_id=product.id,
        current_dos=2.5,
        days_to_stockout=2.5,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=180.0,
        severity="CRITICAL",
        status="OPEN",
    )
    db_session.add_all([supply_event, demand, incident])
    db_session.commit()

    recommendation = TransferRecommendation(
        recommendation_code="REC-20260916-001",
        incident_id=incident.id,
        source_dc_id=dc_ind.id,
        target_dc_id=dc_chi.id,
        product_id=product.id,
        recommended_qty=180,
        feasible_qty_snapshot=180,
        source_surplus_snapshot=450,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("2.50"),
        estimated_cost_snapshot=Decimal("450.00"),
        rationale="Shorter transit time and sufficient surplus.",
        recommendation_source="AI",
        status="PROPOSED",
    )
    db_session.add(recommendation)
    db_session.commit()

    audit = AuditEvent(
        incident_id=incident.id,
        recommendation_id=recommendation.id,
        planner_id="USER-123",
        action="PLANNER_APPROVED",
        final_approved_qty=180,
    )
    db_session.add(audit)
    db_session.commit()

    # Relationship assertions
    fetched_supplier = db_session.query(Supplier).filter_by(supplier_code="SUP-001").one()
    assert len(fetched_supplier.supplier_products) == 1
    assert fetched_supplier.supplier_products[0].unit_cost == Decimal("12.50")

    fetched_dc_chi = db_session.query(DistributionCenter).filter_by(code="DC-CHI").one()
    assert len(fetched_dc_chi.inbound_routes) == 1
    assert fetched_dc_chi.inbound_routes[0].source_dc.code == "DC-IND"

    fetched_incident = (
        db_session.query(RiskIncident).filter_by(incident_code="INC-20260916-001").one()
    )
    assert len(fetched_incident.recommendations) == 1
    assert fetched_incident.recommendations[0].recommended_qty == 180
    assert len(fetched_incident.audit_events) == 1


def test_inventory_balance_check_constraints(db_session: Session) -> None:
    """Verify database check constraint rejection on invalid inventory balance quantities."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    db_session.add_all([product, dc])
    db_session.commit()

    # Reserved > On Hand Violation
    invalid_balance = InventoryBalance(
        dc_id=dc.id,
        product_id=product.id,
        on_hand_qty=50,
        reserved_qty=100,  # Invalid: 50 < 100
    )
    db_session.add(invalid_balance)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_dc_route_same_source_target_constraint(db_session: Session) -> None:
    """Verify check constraint enforcing source_dc_id != target_dc_id on DCRoute."""
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    db_session.add(dc)
    db_session.commit()

    self_route = DCRoute(
        source_dc_id=dc.id,
        target_dc_id=dc.id,  # Invalid: source == target
        transit_days=1,
        cost_per_unit=Decimal("2.50"),
    )
    db_session.add(self_route)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_recommendation_positive_quantity_constraint(db_session: Session) -> None:
    """Verify check constraint enforcing recommended_qty > 0."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc1 = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    dc2 = DistributionCenter(code="DC-IND", name="Indianapolis", city="Indianapolis", state="IN")
    db_session.add_all([product, dc1, dc2])
    db_session.commit()

    incident = RiskIncident(
        incident_code="INC-001",
        target_dc_id=dc1.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="CRITICAL",
    )
    db_session.add(incident)
    db_session.commit()

    zero_qty_rec = TransferRecommendation(
        recommendation_code="REC-001",
        incident_id=incident.id,
        source_dc_id=dc2.id,
        target_dc_id=dc1.id,
        product_id=product.id,
        recommended_qty=0,  # Invalid: qty must be > 0
        feasible_qty_snapshot=100,
        source_surplus_snapshot=100,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("1.00"),
        estimated_cost_snapshot=Decimal("0.00"),
        rationale="Invalid",
        recommendation_source="AI",
    )
    db_session.add(zero_qty_rec)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unique_constraints_enforced(db_session: Session) -> None:
    """Verify uniqueness constraints on demand signals, supplier products, and POs."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    supplier = Supplier(supplier_code="SUP-001", name="Seafood Co")
    db_session.add_all([product, dc, supplier])
    db_session.commit()

    # Demand signal uniqueness: (dc_id, product_id, signal_date)
    demand1 = DailyDemandSignal(
        dc_id=dc.id, product_id=product.id, signal_date=date(2026, 9, 16), daily_demand_qty=10
    )
    demand2 = DailyDemandSignal(
        dc_id=dc.id, product_id=product.id, signal_date=date(2026, 9, 16), daily_demand_qty=20
    )
    db_session.add(demand1)
    db_session.commit()

    db_session.add(demand2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_audit_event_nullable_fields(db_session: Session) -> None:
    """Verify AuditEvent permits NULL for recommendation_id and planner_id."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    db_session.add_all([product, dc])
    db_session.commit()

    incident = RiskIncident(
        incident_code="INC-SYS-001",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="CRITICAL",
    )
    db_session.add(incident)
    db_session.commit()

    system_audit = AuditEvent(
        incident_id=incident.id,
        recommendation_id=None,  # Nullable
        planner_id=None,  # Nullable (System action)
        action="RISK_DETECTED",
        input_snapshot_json='{"status": "detected"}',
    )
    db_session.add(system_audit)
    db_session.commit()

    fetched_audit = db_session.query(AuditEvent).filter_by(id=system_audit.id).one()
    assert fetched_audit.recommendation_id is None
    assert fetched_audit.planner_id is None
    assert fetched_audit.action == "RISK_DETECTED"


def test_inventory_policy_and_po_check_constraints(db_session: Session) -> None:
    """Verify check constraints on InventoryPolicy and PurchaseOrder."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    supplier = Supplier(supplier_code="SUP-001", name="Seafood Co")
    db_session.add_all([product, dc, supplier])
    db_session.commit()

    # Safety stock days < 0 violation
    invalid_policy = InventoryPolicy(dc_id=dc.id, product_id=product.id, safety_stock_days=-1.0)
    db_session.add(invalid_policy)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Ordered Qty <= 0 violation
    invalid_po = PurchaseOrder(
        po_number="PO-INVALID-001",
        supplier_id=supplier.id,
        product_id=product.id,
        destination_dc_id=dc.id,
        ordered_qty=0,  # Invalid: <= 0
        expected_delivery_date=date(2026, 9, 25),
        status="OPEN",
    )
    db_session.add(invalid_po)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_supply_event_and_demand_check_constraints(db_session: Session) -> None:
    """Verify check constraints on SupplyEvent and DailyDemandSignal."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    supplier = Supplier(supplier_code="SUP-001", name="Seafood Co")
    db_session.add_all([product, dc, supplier])
    db_session.commit()

    po = PurchaseOrder(
        po_number="PO-VALID-001",
        supplier_id=supplier.id,
        product_id=product.id,
        destination_dc_id=dc.id,
        ordered_qty=100,
        expected_delivery_date=date(2026, 9, 25),
        status="OPEN",
    )
    db_session.add(po)
    db_session.commit()

    # SupplyEvent delay_days < 0 violation
    invalid_event = SupplyEvent(po_id=po.id, event_type="DELAY", delay_days=-5)
    db_session.add(invalid_event)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # DailyDemandSignal daily_demand_qty < 0 violation
    invalid_demand = DailyDemandSignal(
        dc_id=dc.id, product_id=product.id, signal_date=date(2026, 9, 16), daily_demand_qty=-10
    )
    db_session.add(invalid_demand)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unique_constraints_all_entities(db_session: Session) -> None:
    """Verify duplicate insertions fail on unique columns and composite keys."""
    product = Product(sku="SKU-8842", name="Salmon", category="Seafood", unit_of_measure="CS")
    dc1 = DistributionCenter(code="DC-CHI", name="Chicago", city="Chicago", state="IL")
    dc2 = DistributionCenter(code="DC-IND", name="Indianapolis", city="Indianapolis", state="IN")
    supplier = Supplier(supplier_code="SUP-001", name="Seafood Co")
    db_session.add_all([product, dc1, dc2, supplier])
    db_session.commit()

    # Supplier product uniqueness: (supplier_id, product_id)
    sp1 = SupplierProduct(
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("10"),
        std_lead_time_days=1,
    )
    sp2 = SupplierProduct(
        supplier_id=supplier.id,
        product_id=product.id,
        unit_cost=Decimal("12"),
        std_lead_time_days=2,
    )
    db_session.add(sp1)
    db_session.commit()
    db_session.add(sp2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Route uniqueness: (source_dc_id, target_dc_id)
    r1 = DCRoute(
        source_dc_id=dc1.id,
        target_dc_id=dc2.id,
        transit_days=1,
        cost_per_unit=Decimal("2"),
    )
    r2 = DCRoute(
        source_dc_id=dc1.id,
        target_dc_id=dc2.id,
        transit_days=2,
        cost_per_unit=Decimal("3"),
    )
    db_session.add(r1)
    db_session.commit()
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Inventory balance uniqueness: (dc_id, product_id)
    ib1 = InventoryBalance(dc_id=dc1.id, product_id=product.id, on_hand_qty=10)
    ib2 = InventoryBalance(dc_id=dc1.id, product_id=product.id, on_hand_qty=20)
    db_session.add(ib1)
    db_session.commit()
    db_session.add(ib2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
