"""
Test Business Data Characteristics.
Verifies realistic domain characteristics in seed dataset
(categories, reliability, demand scales, route variations).
"""

from sqlalchemy.orm import Session

from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.supplier import Supplier, SupplierProduct
from app.infrastructure.db.seed.seed import seed_database


def test_business_data_characteristics(test_db: Session) -> None:
    """Verifies that the seeded data displays realistic business characteristics."""
    seed_database(test_db, reset=True)

    # 1. Multiple product categories exist
    categories = {p.category for p in test_db.query(Product).all()}
    expected_categories = {
        "Seafood",
        "Poultry",
        "Beef",
        "Pork",
        "Frozen Foods",
        "Dairy",
        "Produce",
        "Dry Goods",
        "Beverages",
    }
    assert expected_categories.issubset(categories)

    # 2. Multiple suppliers exist with varied reliability
    suppliers = test_db.query(Supplier).all()
    assert len(suppliers) >= 8
    reliabilities = [float(s.reliability_rating) for s in suppliers]
    assert max(reliabilities) >= 0.95
    assert min(reliabilities) <= 0.90
    assert len(set(reliabilities)) >= 4

    # 3. Supplier-Product relationships have realistic lead times
    sps = test_db.query(SupplierProduct).all()
    lead_times = [sp.std_lead_time_days for sp in sps]
    assert min(lead_times) >= 1
    assert max(lead_times) <= 10
    assert len(set(lead_times)) >= 3

    # 4. Distribution Centers have varied active statuses and locations
    dcs = test_db.query(DistributionCenter).all()
    assert len(dcs) >= 8
    inactive_dcs = [dc for dc in dcs if not dc.is_active]
    assert len(inactive_dcs) >= 1  # DC-CMH is inactive for testing filter

    # 5. Routes have varied transit days, costs, and active statuses
    routes = test_db.query(DCRoute).all()
    transit_days = [r.transit_days for r in routes]
    costs = [float(r.cost_per_unit) for r in routes]
    assert min(transit_days) == 1
    assert max(transit_days) >= 3
    assert min(costs) < max(costs)
    inactive_routes = [r for r in routes if not r.is_active]
    assert len(inactive_routes) >= 1  # At least one inactive route

    # 6. Inventory balances show network variations (both high and low balances)
    balances = test_db.query(InventoryBalance).all()
    qty_values = [b.on_hand_qty for b in balances]
    assert min(qty_values) <= 100
    assert max(qty_values) >= 1000
