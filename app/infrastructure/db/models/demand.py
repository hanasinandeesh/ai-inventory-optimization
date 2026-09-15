from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.distribution_center import DistributionCenter
    from app.infrastructure.db.models.product import Product


class DailyDemandSignal(Base):
    """DailyDemandSignal entity recording historical daily demand observations."""

    __tablename__ = "daily_demand_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    daily_demand_qty: Mapped[int] = mapped_column(nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTUAL")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    distribution_center: Mapped["DistributionCenter"] = relationship(
        back_populates="daily_demand_signals"
    )
    product: Mapped["Product"] = relationship(back_populates="daily_demand_signals")

    __table_args__ = (
        UniqueConstraint("dc_id", "product_id", "signal_date", name="uq_demand_dc_product_date"),
        CheckConstraint("daily_demand_qty >= 0", name="ck_demand_qty_nonneg"),
        Index("ix_demand_signals_dc_product_date", "dc_id", "product_id", "signal_date"),
    )
