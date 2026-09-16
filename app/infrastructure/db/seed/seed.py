"""
CLI and program entry point for database seeding.
Applies deterministic golden scenario and synthetic data seeding inside a single transaction.
"""

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from app.core.database import SessionLocal, engine
from app.infrastructure.db.base import Base
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.purchase_order import PurchaseOrder, SupplyEvent
from app.infrastructure.db.models.supplier import Supplier, SupplierProduct
from app.infrastructure.db.seed.golden_scenario import seed_golden_scenario
from app.infrastructure.db.seed.synthetic_data import seed_synthetic_data

logger = logging.getLogger("app.seed")


def reset_database_data(session: Session) -> None:
    """
    Explicitly resets/truncates seed data in reverse foreign key order.
    MUST be explicitly invoked by developer flags (never automated on app startup).
    """
    session.query(SupplyEvent).delete()
    session.query(PurchaseOrder).delete()
    session.query(DailyDemandSignal).delete()
    session.query(InventoryPolicy).delete()
    session.query(InventoryBalance).delete()
    session.query(DCRoute).delete()
    session.query(SupplierProduct).delete()
    session.query(DistributionCenter).delete()
    session.query(Product).delete()
    session.query(Supplier).delete()
    session.flush()


def seed_database(session: Session, reset: bool = False) -> dict[str, int]:
    """
    Executes database seeding inside an explicit transaction.
    Rolls back on error, commits on success.
    """
    try:
        if reset:
            reset_database_data(session)

        golden_ids = seed_golden_scenario(session)
        stats = seed_synthetic_data(session, golden_ids)
        session.commit()
        return stats
    except Exception as exc:
        session.rollback()
        logger.error(f"Seeding failed: {exc}", exc_info=True)
        raise exc


def main() -> None:
    """CLI runner entry point."""
    parser = argparse.ArgumentParser(description="Seed supply-chain database with synthetic data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Explicitly reset existing seed data before seeding.",
    )
    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        stats = seed_database(db, reset=args.reset)
        print("\nSeed completed successfully.\n")
        print(f"Suppliers: {stats['suppliers']}")
        print(f"Products: {stats['products']}")
        print(f"Supplier Products: {stats['supplier_products']}")
        print(f"Distribution Centers: {stats['dcs']}")
        print(f"Routes: {stats['routes']}")
        print(f"Inventory Policies: {stats['policies']}")
        print(f"Inventory Balances: {stats['balances']}")
        print(f"Purchase Orders: {stats['purchase_orders']}")
        print(f"Supply Events: {stats['supply_events']}")
        print(f"Demand Signals: {stats['demand_signals']}\n")
    except Exception as exc:
        print(f"\nSeeding failed with error: {exc}\n", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
