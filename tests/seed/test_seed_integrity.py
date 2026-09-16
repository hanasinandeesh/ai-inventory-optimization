"""
Test Seed Integrity.
Verifies seed completion, FK relationships, unique constraints, and schema validations.
"""

from sqlalchemy.orm import Session

from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.purchase_order import PurchaseOrder, SupplyEvent
from app.infrastructure.db.models.supplier import Supplier
from app.infrastructure.db.seed.seed import seed_database


def test_seed_integrity(test_db: Session) -> None:
    """Verifies that database seeding completes cleanly and respects integrity constraints."""
    stats = seed_database(test_db, reset=True)

    assert stats["suppliers"] >= 8
    assert stats["products"] >= 15
    assert stats["supplier_products"] >= 30
    assert stats["dcs"] >= 6
    assert stats["routes"] >= 15
    assert stats["policies"] >= 50
    assert stats["balances"] >= 50
    assert stats["purchase_orders"] >= 15
    assert stats["supply_events"] >= 5
    assert stats["demand_signals"] >= 700

    # 1. Supplier Integrity
    suppliers = test_db.query(Supplier).all()
    supplier_codes = [s.supplier_code for s in suppliers]
    assert len(supplier_codes) == len(set(supplier_codes))
    for s in suppliers:
        assert 0.0 <= float(s.reliability_rating) <= 1.0

    # 2. Product Integrity
    products = test_db.query(Product).all()
    skus = [p.sku for p in products]
    assert len(skus) == len(set(skus))
    for p in products:
        assert p.pack_size >= 1
        if p.unit_weight_lbs is not None:
            assert float(p.unit_weight_lbs) > 0.0

    # 3. Distribution Center Integrity
    dcs = test_db.query(DistributionCenter).all()
    dc_codes = [dc.code for dc in dcs]
    assert len(dc_codes) == len(set(dc_codes))

    # 4. DC Route Integrity
    routes = test_db.query(DCRoute).all()
    for r in routes:
        assert r.source_dc_id != r.target_dc_id
        assert r.transit_days >= 1
        assert float(r.cost_per_unit) >= 0.0

    # 5. Inventory Balances & Policies Integrity
    balances = test_db.query(InventoryBalance).all()
    for b in balances:
        assert b.on_hand_qty >= 0
        assert b.reserved_qty >= 0

    policies = test_db.query(InventoryPolicy).all()
    for pol in policies:
        assert float(pol.safety_stock_days) >= 0.0
        assert pol.min_reorder_qty > 0

    # 6. Purchase Orders & Supply Events Integrity
    pos = test_db.query(PurchaseOrder).all()
    po_numbers = [po.po_number for po in pos]
    assert len(po_numbers) == len(set(po_numbers))
    for po in pos:
        assert po.ordered_qty > 0

    supply_events = test_db.query(SupplyEvent).all()
    for se in supply_events:
        assert se.delay_days >= 0
        assert se.disrupted_qty >= 0

    # 7. Demand Signals Integrity
    signals = test_db.query(DailyDemandSignal).all()
    for sig in signals:
        assert sig.daily_demand_qty >= 0
