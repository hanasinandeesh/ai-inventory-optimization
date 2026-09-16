import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command


@pytest.fixture(scope="function")
def migrated_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite database file and runs Alembic upgrade head."""
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Run upgrade head
    command.upgrade(alembic_cfg, "head")

    return db_file


def test_alembic_migration_creates_all_13_tables(migrated_db: Path) -> None:
    """Verify fresh database migration creates all 13 V1 entities plus alembic_version."""
    expected_tables = {
        "alembic_version",
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

    conn = sqlite3.connect(migrated_db)
    try:
        tables = {
            t[0]
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert expected_tables.issubset(tables)
        assert len(tables) == 14
    finally:
        conn.close()


def test_alembic_downgrade_and_reupgrade(migrated_db: Path) -> None:
    """Verify downgrade to baseline removes domain tables and re-upgrade restores them cleanly."""
    db_url = f"sqlite:///{migrated_db}"
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Downgrade to 0001_initial_schema
    command.downgrade(alembic_cfg, "0001_initial_schema")

    conn = sqlite3.connect(migrated_db)
    try:
        tables = {
            t[0]
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "suppliers" not in tables
        assert "risk_incidents" not in tables
    finally:
        conn.close()

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")

    conn = sqlite3.connect(migrated_db)
    try:
        tables = {
            t[0]
            for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "suppliers" in tables
        assert "risk_incidents" in tables
    finally:
        conn.close()
