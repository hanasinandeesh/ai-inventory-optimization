"""Initial database baseline migration.

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-15 23:30:00.000000

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Baseline migration placeholder for foundation setup
    pass


def downgrade() -> None:
    pass
