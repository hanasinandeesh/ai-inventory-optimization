from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.distribution_center import DistributionCenter
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.supplier import Supplier


class PurchaseOrder(Base):
    """PurchaseOrder entity representing inbound vendor replenishment orders."""

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordered_qty: Mapped[int] = mapped_column(nullable=False)
    expected_delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    product: Mapped["Product"] = relationship(back_populates="purchase_orders")
    destination_dc: Mapped["DistributionCenter"] = relationship(back_populates="purchase_orders")
    supply_events: Mapped[list["SupplyEvent"]] = relationship(back_populates="purchase_order")

    __table_args__ = (
        CheckConstraint("ordered_qty > 0", name="ck_po_ordered_qty_pos"),
        Index(
            "ix_purchase_orders_supplier_dc_status",
            "supplier_id",
            "destination_dc_id",
            "status",
        ),
    )


class SupplyEvent(Base):
    """SupplyEvent entity representing disruptions or delays affecting a PurchaseOrder."""

    __tablename__ = "supply_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    delay_days: Mapped[int] = mapped_column(nullable=False, default=0)
    disrupted_qty: Mapped[int] = mapped_column(nullable=False, default=0)
    new_expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="supply_events")

    __table_args__ = (
        CheckConstraint("delay_days >= 0", name="ck_supply_event_delay_nonneg"),
        CheckConstraint("disrupted_qty >= 0", name="ck_supply_event_disrupted_nonneg"),
    )
