"""
Synthetic Data Generator for Food-Service Distribution Business.
Generates realistic suppliers, products, DCs, routes, inventory policies,
inventory balances, purchase orders, supply events, and 14-day demand signals.
"""

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.purchase_order import PurchaseOrder, SupplyEvent
from app.infrastructure.db.models.supplier import Supplier, SupplierProduct


def seed_synthetic_data(session: Session, golden_ids: dict[str, int]) -> dict[str, int]:
    """
    Seeds general synthetic supply chain data deterministically.
    """
    rng = random.Random(42)

    # 1. Additional Suppliers (7 synthetic suppliers + 1 golden supplier = 8 total)
    suppliers_data = [
        ("SUP-002", "Midwest Protein Distributors", Decimal("0.92")),
        ("SUP-003", "Great Lakes Dairy Supply", Decimal("0.95")),
        ("SUP-004", "Prairie Fresh Foods", Decimal("0.88")),
        ("SUP-005", "National Frozen Foods", Decimal("0.90")),
        ("SUP-006", "Heartland Produce Co.", Decimal("0.85")),
        ("SUP-007", "Apex Beverage Group", Decimal("0.94")),
        ("SUP-008", "Buckeye Dry Goods", Decimal("0.89")),
    ]

    supplier_objs: list[Supplier] = []
    for code, name, rel in suppliers_data:
        sup = Supplier(supplier_code=code, name=name, reliability_rating=rel, is_active=True)
        session.add(sup)
        supplier_objs.append(sup)
    session.flush()

    # 2. Additional Products (17 synthetic products + 1 golden = 18 total)
    products_data = [
        # (sku, name, category, uom, pack_size, weight, category_type)
        (
            "SKU-1001",
            "Chicken Breast Boneless Skinless - 40lb Case",
            "Poultry",
            "CS",
            1,
            Decimal("40.00"),
            "high",
        ),
        ("SKU-1002", "Ground Turkey - 30lb Case", "Poultry", "CS", 1, Decimal("30.00"), "mod"),
        ("SKU-2001", "Ground Beef 80/20 - 40lb Case", "Beef", "CS", 1, Decimal("40.00"), "high"),
        ("SKU-2002", "Beef Ribeye Choice - 20lb Case", "Beef", "CS", 1, Decimal("20.00"), "low"),
        ("SKU-2003", "Pork Loin Boneless - 30lb Case", "Pork", "CS", 1, Decimal("30.00"), "mod"),
        (
            "SKU-3001",
            "Frozen French Fries - 30lb Case",
            "Frozen Foods",
            "CS",
            1,
            Decimal("30.00"),
            "high",
        ),
        (
            "SKU-3002",
            "Frozen Mixed Vegetables - 20lb Case",
            "Frozen Foods",
            "CS",
            1,
            Decimal("20.00"),
            "mod",
        ),
        (
            "SKU-4001",
            "Mozzarella Cheese Shredded - 20lb Case",
            "Dairy",
            "CS",
            1,
            Decimal("20.00"),
            "mod",
        ),
        (
            "SKU-4002",
            "Whole Milk 3.25% - 4 x 1 Gal Case",
            "Dairy",
            "CS",
            4,
            Decimal("34.00"),
            "high",
        ),
        ("SKU-4003", "Unsalted Butter - 36 x 1lb Case", "Dairy", "CS", 36, Decimal("36.00"), "mod"),
        ("SKU-5001", "Roma Tomatoes - 25lb Case", "Produce", "CS", 1, Decimal("25.00"), "mod"),
        ("SKU-5002", "Yellow Onions - 50lb Bag", "Produce", "BAG", 1, Decimal("50.00"), "high"),
        (
            "SKU-6001",
            "All-Purpose Flour - 50lb Bag",
            "Dry Goods",
            "BAG",
            1,
            Decimal("50.00"),
            "high",
        ),
        (
            "SKU-6002",
            "Extra Virgin Olive Oil - 6 x 1L Case",
            "Dry Goods",
            "CS",
            6,
            Decimal("14.00"),
            "low",
        ),
        ("SKU-6003", "Granulated Sugar - 50lb Bag", "Dry Goods", "BAG", 1, Decimal("50.00"), "mod"),
        (
            "SKU-7001",
            "100% Orange Juice - 12 x 1L Case",
            "Beverages",
            "CS",
            12,
            Decimal("28.00"),
            "mod",
        ),
        (
            "SKU-8001",
            "White Shrimp 16/20 Peeled - 10lb Case",
            "Seafood",
            "CS",
            1,
            Decimal("10.00"),
            "low",
        ),
    ]

    product_objs: list[Product] = []
    for sku, name, cat, uom, pack, weight, _vol in products_data:
        p = Product(
            sku=sku,
            name=name,
            category=cat,
            unit_of_measure=uom,
            pack_size=pack,
            unit_weight_lbs=weight,
        )
        session.add(p)
        product_objs.append(p)
    session.flush()

    # 3. Supplier Product Relationships (35–40 total)
    # Map suppliers to product categories realistically
    all_suppliers = [session.get(Supplier, golden_ids["supplier_id"])] + supplier_objs
    all_products = [session.get(Product, golden_ids["product_id"])] + product_objs

    supplier_map = {s.name: s for s in all_suppliers}
    product_map = {p.sku: p for p in all_products}

    supplier_product_configs = [
        # (supplier_name, sku, unit_cost, std_lead_time_days, min_order_qty, is_primary)
        ("NorthStar Seafood Supply", "SKU-8001", "85.00", 4, 10, True),
        ("Midwest Protein Distributors", "SKU-1001", "55.00", 3, 20, True),
        ("Midwest Protein Distributors", "SKU-1002", "42.00", 3, 15, True),
        ("Midwest Protein Distributors", "SKU-2001", "68.00", 2, 25, True),
        ("Midwest Protein Distributors", "SKU-2002", "145.00", 4, 5, True),
        ("Midwest Protein Distributors", "SKU-2003", "48.00", 3, 15, True),
        ("Prairie Fresh Foods", "SKU-1001", "57.50", 4, 30, False),  # Secondary for Chicken
        ("Prairie Fresh Foods", "SKU-2001", "71.00", 3, 30, False),  # Secondary for Beef
        ("Great Lakes Dairy Supply", "SKU-4001", "46.00", 2, 15, True),
        ("Great Lakes Dairy Supply", "SKU-4002", "18.50", 1, 40, True),
        ("Great Lakes Dairy Supply", "SKU-4003", "92.00", 2, 10, True),
        ("National Frozen Foods", "SKU-3001", "22.00", 4, 50, True),
        ("National Frozen Foods", "SKU-3002", "26.00", 4, 30, True),
        ("Heartland Produce Co.", "SKU-5001", "28.00", 2, 20, True),
        ("Heartland Produce Co.", "SKU-5002", "19.50", 2, 25, True),
        ("Buckeye Dry Goods", "SKU-6001", "21.00", 5, 40, True),
        ("Buckeye Dry Goods", "SKU-6002", "64.00", 5, 10, True),
        ("Buckeye Dry Goods", "SKU-6003", "24.50", 5, 30, True),
        ("Apex Beverage Group", "SKU-7001", "31.00", 3, 25, True),
        # Additional secondary/backup mappings
        ("National Frozen Foods", "SKU-7001", "32.50", 4, 30, False),
        ("Prairie Fresh Foods", "SKU-5001", "29.50", 3, 20, False),
        ("Buckeye Dry Goods", "SKU-4003", "95.00", 4, 15, False),
        ("Midwest Protein Distributors", "SKU-8842", "47.00", 4, 15, False),
        ("Heartland Produce Co.", "SKU-3002", "27.50", 3, 25, False),
        ("Apex Beverage Group", "SKU-4002", "19.20", 2, 50, False),
        ("NorthStar Seafood Supply", "SKU-3001", "23.50", 5, 40, False),
        ("Prairie Fresh Foods", "SKU-2003", "50.00", 4, 20, False),
        ("Buckeye Dry Goods", "SKU-5002", "20.50", 3, 30, False),
        ("Great Lakes Dairy Supply", "SKU-7001", "32.00", 3, 20, False),
        ("National Frozen Foods", "SKU-8001", "88.00", 5, 10, False),
        ("Heartland Produce Co.", "SKU-6003", "25.50", 4, 25, False),
        ("Midwest Protein Distributors", "SKU-8001", "89.00", 5, 10, False),
        ("Apex Beverage Group", "SKU-6002", "66.00", 4, 12, False),
        ("Prairie Fresh Foods", "SKU-4001", "48.00", 3, 20, False),
        ("Buckeye Dry Goods", "SKU-3001", "23.00", 4, 40, False),
        ("National Frozen Foods", "SKU-4003", "94.00", 3, 12, False),
    ]

    sp_count = 0
    for s_name, sku, cost, lead, min_qty, is_pri in supplier_product_configs:
        sup = supplier_map[s_name]
        prod = product_map[sku]
        sp = SupplierProduct(
            supplier_id=sup.id,
            product_id=prod.id,
            supplier_sku=f"{sup.supplier_code}-{prod.sku}",
            unit_cost=Decimal(cost),
            std_lead_time_days=lead,
            min_order_qty=min_qty,
            is_primary=is_pri,
        )
        session.add(sp)
        sp_count += 1
    session.flush()

    # 4. Additional Distribution Centers (5 synthetic + 3 golden = 8 total)
    # CMH (Columbus, OH) is set to is_active=False per requirement
    dcs_data = [
        ("DC-ATL", "Atlanta Distribution Center", "Atlanta", "GA", True),
        ("DC-DEN", "Denver Distribution Center", "Denver", "CO", True),
        ("DC-MEM", "Memphis Distribution Center", "Memphis", "TN", True),
        ("DC-KC", "Kansas City Distribution Center", "Kansas City", "MO", True),
        ("DC-CMH", "Columbus Distribution Center", "Columbus", "OH", False),  # Inactive DC
    ]

    dc_objs: list[DistributionCenter] = []
    for code, name, city, state, active in dcs_data:
        dc = DistributionCenter(code=code, name=name, city=city, state=state, is_active=active)
        session.add(dc)
        dc_objs.append(dc)
    session.flush()

    all_dcs = [
        session.get(DistributionCenter, golden_ids["chi_dc_id"]),
        session.get(DistributionCenter, golden_ids["ind_dc_id"]),
        session.get(DistributionCenter, golden_ids["dal_dc_id"]),
    ] + dc_objs
    dc_map = {dc.code: dc for dc in all_dcs}

    # 5. Routes (20 total: 2 golden + 18 synthetic)
    routes_data = [
        # (source, target, transit_days, cost_per_unit, distance_miles, is_active)
        ("DC-IND", "DC-ATL", 2, "4.20", "530.00", True),
        ("DC-IND", "DC-DEN", 3, "6.50", "1080.00", True),
        ("DC-IND", "DC-MEM", 1, "3.10", "470.00", True),
        ("DC-IND", "DC-KC", 2, "4.00", "500.00", True),
        ("DC-MEM", "DC-CHI", 2, "3.80", "530.00", True),
        ("DC-MEM", "DC-ATL", 1, "2.80", "390.00", True),
        ("DC-MEM", "DC-DAL", 2, "4.10", "450.00", True),
        ("DC-KC", "DC-CHI", 2, "3.90", "510.00", True),
        ("DC-KC", "DC-DEN", 2, "4.50", "600.00", True),
        ("DC-KC", "DC-ATL", 3, "5.20", "800.00", False),  # Inactive route (Scenario F)
        ("DC-DEN", "DC-CHI", 3, "7.10", "1000.00", True),  # Slow route (Scenario E)
        ("DC-DEN", "DC-DAL", 2, "5.40", "660.00", True),
        ("DC-ATL", "DC-CHI", 2, "4.80", "710.00", True),
        ("DC-ATL", "DC-MEM", 1, "2.90", "390.00", True),
        ("DC-DAL", "DC-MEM", 2, "4.30", "450.00", True),
        ("DC-DAL", "DC-DEN", 2, "5.50", "660.00", True),
        ("DC-CMH", "DC-CHI", 1, "2.40", "350.00", True),  # Route from inactive DC
        ("DC-CHI", "DC-IND", 1, "2.50", "180.00", True),
    ]

    for src_code, tgt_code, transit, cost, dist, active in routes_data:
        src = dc_map[src_code]
        tgt = dc_map[tgt_code]
        r = DCRoute(
            source_dc_id=src.id,
            target_dc_id=tgt.id,
            transit_days=transit,
            cost_per_unit=Decimal(cost),
            distance_miles=Decimal(dist) if dist else None,
            is_active=active,
        )
        session.add(r)
    session.flush()

    # 6. Inventory Balances, Policies & 14-Day Demand Signals for Intentional Scenarios A - G
    # Plus broader operational coverage to reach ~75 policies and ~75 balances
    detection_date = date(2026, 9, 16)
    start_date = detection_date - timedelta(days=13)

    # Specific Intentional Scenarios:
    # Scenario A: Normal Inventory (Chicken Breast at DC-ATL)
    # Scenario B: Low Inventory (Ground Beef at DC-DEN)
    # Scenario C: Excess Inventory (Frozen French Fries at DC-MEM)
    # Scenario D: No Source Surplus (Roma Tomatoes at DC-ATL)
    # Scenario E: Transit Too Slow (Olive Oil at DC-CHI)
    # Scenario F: Inactive Route (Mozzarella Cheese at DC-ATL)
    # Scenario G: Missing Operational Data (All-Purpose Flour at DC-MEM - balance without policy)

    scenario_configs = [
        # Scenario A: Normal (SKU-1001 @ DC-ATL) -> Available=800, Shortage=0,
        # SafetyStock=5 days
        ("SKU-1001", "DC-ATL", 800, 0, 5.0, 50, "steady"),
        # Scenario B: Low Inventory (SKU-2001 @ DC-DEN) -> Available=120, Shortage=60
        ("SKU-2001", "DC-DEN", 120, 0, 6.0, 30, "steady"),
        # Scenario C: Excess Inventory (SKU-3001 @ DC-MEM) -> Available=2500,
        # Surplus=2300
        ("SKU-3001", "DC-MEM", 2500, 0, 5.0, 40, "steady"),
        # Scenario D: No Source Surplus (SKU-5001 @ DC-ATL) -> Available=50,
        # Shortage=50
        ("SKU-5001", "DC-ATL", 50, 0, 4.0, 25, "steady"),
        ("SKU-5001", "DC-MEM", 40, 0, 4.0, 25, "steady"),  # No surplus
        ("SKU-5001", "DC-KC", 30, 0, 4.0, 25, "steady"),  # No surplus
        # Scenario E: Transit Too Slow (SKU-6002 @ DC-CHI) -> Available=20,
        # Shortage=40, DUS=1.0 day
        # Source DC-DEN has surplus=500, but route DEN->CHI transit=3 days >= 1.0 day
        ("SKU-6002", "DC-CHI", 20, 0, 3.0, 20, "steady"),
        ("SKU-6002", "DC-DEN", 600, 0, 3.0, 20, "steady"),  # Surplus 540
        # Scenario F: Inactive Route (SKU-4001 @ DC-ATL) -> Shortage=90,
        # DUS=1.0 day
        # Source DC-KC has surplus=500, but route KC->ATL is_active=False
        ("SKU-4001", "DC-ATL", 30, 0, 4.0, 30, "steady"),
        ("SKU-4001", "DC-KC", 650, 0, 4.0, 30, "steady"),  # Surplus 530
        # Scenario G: Missing Operational Data (SKU-6001 @ DC-MEM) -> Balance
        # exists, NO policy!
        ("SKU-6001", "DC-MEM", 400, 0, None, 45, "steady"),  # None for policy
    ]

    # Add broad operational SKU/DC pairs to reach ~75 total policies and balances
    all_active_dcs = [dc for dc in all_dcs if dc.is_active]
    base_skus = [p for p in all_products if p.sku != "SKU-8842"]

    broad_pairs: list[tuple[str, str, int, int, float | None, int, str]] = []
    for prod in base_skus:
        for dc in all_active_dcs:
            # Skip if already in scenario_configs
            if any(sc[0] == prod.sku and sc[1] == dc.code for sc in scenario_configs):
                continue
            # Pick ~60% of combinations to keep dataset realistic and sparse
            if rng.random() < 0.60:
                base_demand = rng.randint(15, 60)
                ss_days = round(rng.uniform(3.0, 8.0), 1)
                target_ss = base_demand * ss_days
                # Generate random balance ratio relative to safety stock
                balance_mult = rng.choice([0.4, 0.7, 1.2, 1.5, 2.2, 3.0])
                on_hand = int(target_ss * balance_mult)
                pattern = rng.choice(
                    ["steady", "growing", "declining", "weekly", "spike", "volatile"]
                )
                broad_pairs.append((prod.sku, dc.code, on_hand, 0, ss_days, base_demand, pattern))

    all_configs = scenario_configs + broad_pairs

    policy_count = 0
    balance_count = 0
    demand_signal_count = 0

    for sku, dc_code, on_hand, reserved, ss_days, base_demand, pattern in all_configs:
        prod = product_map[sku]
        dc = dc_map[dc_code]

        # Balance
        bal = InventoryBalance(
            dc_id=dc.id, product_id=prod.id, on_hand_qty=on_hand, reserved_qty=reserved
        )
        session.add(bal)
        balance_count += 1

        # Policy (if ss_days is not None)
        if ss_days is not None:
            pol = InventoryPolicy(
                dc_id=dc.id,
                product_id=prod.id,
                safety_stock_days=ss_days,
                min_reorder_qty=rng.randint(20, 100),
                is_active=True,
            )
            session.add(pol)
            policy_count += 1

        # 14-Day Demand Signals
        for day_idx in range(14):
            sig_date = start_date + timedelta(days=day_idx)
            if pattern == "steady":
                qty = base_demand + rng.randint(-2, 2)
            elif pattern == "growing":
                qty = base_demand + (day_idx * 2) + rng.randint(-1, 1)
            elif pattern == "declining":
                qty = max(5, base_demand - (day_idx * 2) + rng.randint(-1, 1))
            elif pattern == "weekly":
                # Higher on weekdays (0-4), lower on weekends (5-6)
                weekday = sig_date.weekday()
                mult = 1.2 if weekday < 5 else 0.6
                qty = int(base_demand * mult) + rng.randint(-2, 2)
            elif pattern == "spike":
                qty = base_demand * 2 if day_idx in (10, 11) else base_demand + rng.randint(-2, 2)
            elif pattern == "volatile":
                qty = max(5, base_demand + rng.randint(-12, 12))
            else:
                qty = base_demand

            qty = max(0, qty)
            session.add(
                DailyDemandSignal(
                    dc_id=dc.id, product_id=prod.id, signal_date=sig_date, daily_demand_qty=qty
                )
            )
            demand_signal_count += 1

    session.flush()

    # 7. Purchase Orders (15-30 total)
    po_statuses = ["OPEN", "CONFIRMED", "IN_TRANSIT", "DELIVERED", "DELAYED"]
    po_objs: list[PurchaseOrder] = []

    for i in range(1, 23):
        po_num = f"PO-2026-{i:04d}"
        sup = rng.choice(all_suppliers)
        prod = rng.choice(all_products)
        dest_dc = rng.choice(all_active_dcs)
        status = rng.choice(po_statuses)
        deliv_date = detection_date + timedelta(days=rng.randint(-5, 10))

        po = PurchaseOrder(
            po_number=po_num,
            supplier_id=sup.id,
            product_id=prod.id,
            destination_dc_id=dest_dc.id,
            ordered_qty=rng.randint(100, 1000),
            expected_delivery_date=deliv_date,
            status=status,
            created_at=datetime.now(UTC) - timedelta(days=rng.randint(1, 15)),
        )
        session.add(po)
        po_objs.append(po)
    session.flush()

    # 8. Supply Events (5-15 total)
    event_types = ["SUPPLIER_DELAY", "PARTIAL_SHORTAGE", "LOGISTICS_DELAY"]
    delayed_pos = [po for po in po_objs if po.status in ("DELAYED", "IN_TRANSIT")]
    se_count = 0

    for po in delayed_pos[:8]:
        ev_type = rng.choice(event_types)
        delay = rng.randint(2, 7) if ev_type in ("SUPPLIER_DELAY", "LOGISTICS_DELAY") else 0
        disrupted = rng.randint(50, 200) if ev_type == "PARTIAL_SHORTAGE" else 0
        new_date = (
            po.expected_delivery_date + timedelta(days=delay)
            if delay > 0
            else po.expected_delivery_date
        )

        se = SupplyEvent(
            po_id=po.id,
            event_type=ev_type,
            delay_days=delay,
            disrupted_qty=disrupted,
            new_expected_date=new_date,
            notes=f"Disruption event: {ev_type} affecting {po.po_number}",
        )
        session.add(se)
        se_count += 1
    session.flush()

    return {
        "suppliers": len(all_suppliers),
        "products": len(all_products),
        "supplier_products": sp_count + 1,  # +1 golden
        "dcs": len(all_dcs),
        "routes": len(routes_data) + 2,  # +2 golden
        "policies": policy_count + 3,  # +3 golden
        "balances": balance_count + 3,  # +3 golden
        "purchase_orders": len(po_objs),
        "supply_events": se_count,
        "demand_signals": demand_signal_count + 42,  # +42 golden (14 * 3)
    }
