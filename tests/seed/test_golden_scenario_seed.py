"""
Test Golden Scenario Seed.
Verifies exact database state established for the Golden Scenario without runtime entities.
"""

from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database


def test_golden_scenario_seed_verification(test_db: Session) -> None:
    """Verifies that the Golden Scenario underlying database state is correctly seeded."""
    seed_database(test_db, reset=True)

    # 1. Product SKU-8842
    product = test_db.query(Product).filter(Product.sku == "SKU-8842").first()
    assert product is not None
    assert product.name == "Atlantic Salmon Fillets - 10lb Case"

    # 2. DCs: DC-CHI, DC-IND, DC-DAL
    dc_chi = test_db.query(DistributionCenter).filter(DistributionCenter.code == "DC-CHI").first()
    dc_ind = test_db.query(DistributionCenter).filter(DistributionCenter.code == "DC-IND").first()
    dc_dal = test_db.query(DistributionCenter).filter(DistributionCenter.code == "DC-DAL").first()

    assert dc_chi is not None
    assert dc_ind is not None
    assert dc_dal is not None

    # 3. Inventory Balances
    bal_chi = (
        test_db.query(InventoryBalance).filter_by(dc_id=dc_chi.id, product_id=product.id).first()
    )
    bal_ind = (
        test_db.query(InventoryBalance).filter_by(dc_id=dc_ind.id, product_id=product.id).first()
    )
    bal_dal = (
        test_db.query(InventoryBalance).filter_by(dc_id=dc_dal.id, product_id=product.id).first()
    )

    assert bal_chi.on_hand_qty == 100
    assert bal_chi.reserved_qty == 0

    assert bal_ind.on_hand_qty == 650
    assert bal_ind.reserved_qty == 0

    assert bal_dal.on_hand_qty == 1000
    assert bal_dal.reserved_qty == 0

    # 4. Inventory Policies
    pol_chi = (
        test_db.query(InventoryPolicy).filter_by(dc_id=dc_chi.id, product_id=product.id).first()
    )
    pol_ind = (
        test_db.query(InventoryPolicy).filter_by(dc_id=dc_ind.id, product_id=product.id).first()
    )
    pol_dal = (
        test_db.query(InventoryPolicy).filter_by(dc_id=dc_dal.id, product_id=product.id).first()
    )

    assert float(pol_chi.safety_stock_days) == 7.0
    assert float(pol_ind.safety_stock_days) == 5.0
    assert float(pol_dal.safety_stock_days) == 7.5

    # 5. Demand Signals (14 per DC for SKU-8842)
    sig_chi = (
        test_db.query(DailyDemandSignal).filter_by(dc_id=dc_chi.id, product_id=product.id).all()
    )
    sig_ind = (
        test_db.query(DailyDemandSignal).filter_by(dc_id=dc_ind.id, product_id=product.id).all()
    )
    sig_dal = (
        test_db.query(DailyDemandSignal).filter_by(dc_id=dc_dal.id, product_id=product.id).all()
    )

    assert len(sig_chi) == 14
    assert len(sig_ind) == 14
    assert len(sig_dal) == 14

    for s in sig_chi + sig_ind + sig_dal:
        assert s.daily_demand_qty == 40

    # 6. Routes to Chicago
    route_ind = (
        test_db.query(DCRoute).filter_by(source_dc_id=dc_ind.id, target_dc_id=dc_chi.id).first()
    )
    route_dal = (
        test_db.query(DCRoute).filter_by(source_dc_id=dc_dal.id, target_dc_id=dc_chi.id).first()
    )

    assert route_ind.transit_days == 1
    assert float(route_ind.cost_per_unit) == 2.50

    assert route_dal.transit_days == 3
    assert float(route_dal.cost_per_unit) == 7.78

    # 7. CRITICAL VERIFICATION: No runtime entities created during seeding!
    assert test_db.query(RiskIncident).count() == 0
    assert test_db.query(TransferRecommendation).count() == 0
    assert test_db.query(AuditEvent).count() == 0
