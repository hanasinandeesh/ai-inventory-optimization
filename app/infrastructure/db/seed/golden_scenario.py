"""
Golden Demo Scenario Generator for Inventory Optimization System.
Establishes underlying database state ONLY for the Golden Scenario:
- SKU-8842 (Atlantic Salmon Fillets - 10lb Case)
- Target: Chicago DC (DC-CHI)
  [Available=100, Demand=40/day, SafetyStock=7 days -> Shortage=180, DUS=2.5, CRITICAL]
- Source 1: Indianapolis DC (DC-IND)
  [Available=650, Demand=40/day, SafetyStock=5 days -> Surplus=450, Transit=1 day, Cost=$2.50]
- Source 2: Dallas DC (DC-DAL)
  [Available=1000, Demand=40/day, SafetyStock=7.5 days -> Surplus=700, Transit=3 days, Cost=$7.78]

Does NOT create RiskIncident, TransferRecommendation, or AuditEvent.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.supplier import Supplier, SupplierProduct


def seed_golden_scenario(session: Session) -> dict[str, int]:
    """
    Seeds the deterministic Golden Scenario entities and returns created object IDs.
    """
    # 1. Product: SKU-8842
    product = Product(
        sku="SKU-8842",
        name="Atlantic Salmon Fillets - 10lb Case",
        category="Seafood",
        unit_of_measure="CS",
        pack_size=1,
        unit_weight_lbs=Decimal("10.00"),
    )
    session.add(product)
    session.flush()

    # 2. Primary Supplier: NorthStar Seafood Supply
    supplier = Supplier(
        supplier_code="SUP-001",
        name="NorthStar Seafood Supply",
        reliability_rating=Decimal("0.96"),
        is_active=True,
    )
    session.add(supplier)
    session.flush()

    supplier_product = SupplierProduct(
        supplier_id=supplier.id,
        product_id=product.id,
        supplier_sku="SUP-SKU-8842",
        unit_cost=Decimal("45.00"),
        std_lead_time_days=3,
        min_order_qty=10,
        is_primary=True,
    )
    session.add(supplier_product)

    # 3. Distribution Centers
    dc_chi = DistributionCenter(
        code="DC-CHI",
        name="Chicago Distribution Center",
        city="Chicago",
        state="IL",
        is_active=True,
    )
    dc_ind = DistributionCenter(
        code="DC-IND",
        name="Indianapolis Distribution Center",
        city="Indianapolis",
        state="IN",
        is_active=True,
    )
    dc_dal = DistributionCenter(
        code="DC-DAL", name="Dallas Distribution Center", city="Dallas", state="TX", is_active=True
    )
    session.add_all([dc_chi, dc_ind, dc_dal])
    session.flush()

    # 4. Inventory Balances
    # Chicago: Available = 100
    bal_chi = InventoryBalance(
        dc_id=dc_chi.id, product_id=product.id, on_hand_qty=100, reserved_qty=0
    )
    # Indianapolis: Available = 650
    bal_ind = InventoryBalance(
        dc_id=dc_ind.id, product_id=product.id, on_hand_qty=650, reserved_qty=0
    )
    # Dallas: Available = 1000
    bal_dal = InventoryBalance(
        dc_id=dc_dal.id, product_id=product.id, on_hand_qty=1000, reserved_qty=0
    )
    session.add_all([bal_chi, bal_ind, bal_dal])

    # 5. Inventory Policies
    # Chicago: 7 days safety stock (7 * 40 = 280 target safety stock)
    pol_chi = InventoryPolicy(
        dc_id=dc_chi.id,
        product_id=product.id,
        safety_stock_days=7.0,
        min_reorder_qty=50,
        is_active=True,
    )
    # Indianapolis: 5 days safety stock (5 * 40 = 200 safety stock -> 650 - 200 = 450 surplus)
    pol_ind = InventoryPolicy(
        dc_id=dc_ind.id,
        product_id=product.id,
        safety_stock_days=5.0,
        min_reorder_qty=50,
        is_active=True,
    )
    # Dallas: 7.5 days safety stock (7.5 * 40 = 300 safety stock -> 1000 - 300 = 700 surplus)
    pol_dal = InventoryPolicy(
        dc_id=dc_dal.id,
        product_id=product.id,
        safety_stock_days=7.5,
        min_reorder_qty=50,
        is_active=True,
    )
    session.add_all([pol_chi, pol_ind, pol_dal])

    # 6. Routes to Chicago
    # Indianapolis -> Chicago: 1 day transit, $2.50 cost
    route_ind = DCRoute(
        source_dc_id=dc_ind.id,
        target_dc_id=dc_chi.id,
        transit_days=1,
        cost_per_unit=Decimal("2.50"),
        distance_miles=Decimal("180.00"),
        is_active=True,
    )
    # Dallas -> Chicago: 3 days transit, $7.78 cost
    route_dal = DCRoute(
        source_dc_id=dc_dal.id,
        target_dc_id=dc_chi.id,
        transit_days=3,
        cost_per_unit=Decimal("7.78"),
        distance_miles=Decimal("925.00"),
        is_active=True,
    )
    session.add_all([route_ind, route_dal])

    # 7. Exactly 14 Daily Demand Signals for Chicago, Indy, Dallas (averaging 40/day)
    detection_date = date(2026, 9, 16)
    start_date = detection_date - timedelta(days=13)

    for i in range(14):
        signal_date = start_date + timedelta(days=i)
        # Exactly 40 cases per day
        session.add(
            DailyDemandSignal(
                dc_id=dc_chi.id, product_id=product.id, signal_date=signal_date, daily_demand_qty=40
            )
        )
        session.add(
            DailyDemandSignal(
                dc_id=dc_ind.id, product_id=product.id, signal_date=signal_date, daily_demand_qty=40
            )
        )
        session.add(
            DailyDemandSignal(
                dc_id=dc_dal.id, product_id=product.id, signal_date=signal_date, daily_demand_qty=40
            )
        )

    session.flush()

    return {
        "product_id": product.id,
        "supplier_id": supplier.id,
        "chi_dc_id": dc_chi.id,
        "ind_dc_id": dc_ind.id,
        "dal_dc_id": dc_dal.id,
    }
