from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.distribution_center import DistributionCenter
    from app.infrastructure.db.models.product import Product


class InventoryPolicy(Base):
    """InventoryPolicy entity setting target safety stock levels for SKU/DC pairs."""

    __tablename__ = "inventory_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    safety_stock_days: Mapped[float] = mapped_column(Float, nullable=False)
    min_reorder_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    distribution_center: Mapped["DistributionCenter"] = relationship(
        back_populates="inventory_policies"
    )
    product: Mapped["Product"] = relationship(back_populates="inventory_policies")

    __table_args__ = (
        UniqueConstraint("dc_id", "product_id", name="uq_inventory_policy_dc_product"),
        CheckConstraint("safety_stock_days >= 0", name="ck_inv_policy_safety_days_nonneg"),
        CheckConstraint("min_reorder_qty >= 0", name="ck_inv_policy_min_reorder_nonneg"),
    )


class InventoryBalance(Base):
    """
    InventoryBalance entity tracking physical on-hand and reserved stock levels.
    NOTE: Business calculations and inventory mutations belong exclusively in the domain layer.
    """

    __tablename__ = "inventory_balances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    on_hand_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    reserved_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    distribution_center: Mapped["DistributionCenter"] = relationship(
        back_populates="inventory_balances"
    )
    product: Mapped["Product"] = relationship(back_populates="inventory_balances")

    __table_args__ = (
        UniqueConstraint("dc_id", "product_id", name="uq_inventory_balance_dc_product"),
        CheckConstraint("on_hand_qty >= 0", name="ck_inv_balance_on_hand_nonneg"),
        CheckConstraint("reserved_qty >= 0", name="ck_inv_balance_reserved_nonneg"),
        CheckConstraint(
            "on_hand_qty >= reserved_qty", name="ck_inv_balance_on_hand_ge_reserved"
        ),
        Index("ix_inventory_balances_dc_product", "dc_id", "product_id"),
    )
