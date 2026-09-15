from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.purchase_order import PurchaseOrder


class Supplier(Base):
    """Supplier entity representing external product vendors."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reliability_rating: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("1.00")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    supplier_products: Mapped[list["SupplierProduct"]] = relationship(
        back_populates="supplier"
    )
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="supplier"
    )


class SupplierProduct(Base):
    """SupplierProduct cross-reference entity linking suppliers to products."""

    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    std_lead_time_days: Mapped[int] = mapped_column(nullable=False)
    min_order_qty: Mapped[int] = mapped_column(nullable=False, default=1)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="supplier_products")
    product: Mapped["Product"] = relationship(back_populates="supplier_products")

    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),
        CheckConstraint("unit_cost >= 0", name="ck_supplier_product_cost_nonneg"),
        CheckConstraint("std_lead_time_days >= 0", name="ck_supplier_product_lead_time_nonneg"),
        CheckConstraint("min_order_qty > 0", name="ck_supplier_product_min_qty_pos"),
    )
