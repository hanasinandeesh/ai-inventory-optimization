from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.demand import DailyDemandSignal
    from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
    from app.infrastructure.db.models.purchase_order import PurchaseOrder
    from app.infrastructure.db.models.recommendation import TransferRecommendation
    from app.infrastructure.db.models.risk import RiskIncident


class DistributionCenter(Base):
    """DistributionCenter entity representing fulfillment nodes/warehouses."""

    __tablename__ = "distribution_centers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    outbound_routes: Mapped[list["DCRoute"]] = relationship(
        foreign_keys="[DCRoute.source_dc_id]", back_populates="source_dc"
    )
    inbound_routes: Mapped[list["DCRoute"]] = relationship(
        foreign_keys="[DCRoute.target_dc_id]", back_populates="target_dc"
    )
    inventory_policies: Mapped[list["InventoryPolicy"]] = relationship(
        back_populates="distribution_center"
    )
    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(
        back_populates="distribution_center"
    )
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="destination_dc"
    )
    daily_demand_signals: Mapped[list["DailyDemandSignal"]] = relationship(
        back_populates="distribution_center"
    )
    risk_incidents: Mapped[list["RiskIncident"]] = relationship(
        back_populates="target_dc"
    )
    outbound_recommendations: Mapped[list["TransferRecommendation"]] = relationship(
        foreign_keys="[TransferRecommendation.source_dc_id]", back_populates="source_dc"
    )
    inbound_recommendations: Mapped[list["TransferRecommendation"]] = relationship(
        foreign_keys="[TransferRecommendation.target_dc_id]", back_populates="target_dc"
    )


class DCRoute(Base):
    """DCRoute entity representing directed transportation links between DCs."""

    __tablename__ = "dc_routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transit_days: Mapped[int] = mapped_column(nullable=False)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    distance_miles: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    source_dc: Mapped["DistributionCenter"] = relationship(
        foreign_keys=[source_dc_id], back_populates="outbound_routes"
    )
    target_dc: Mapped["DistributionCenter"] = relationship(
        foreign_keys=[target_dc_id], back_populates="inbound_routes"
    )

    __table_args__ = (
        UniqueConstraint("source_dc_id", "target_dc_id", name="uq_dc_route_source_target"),
        CheckConstraint("source_dc_id != target_dc_id", name="ck_dc_route_diff_dcs"),
        CheckConstraint("transit_days >= 1", name="ck_dc_route_transit_days_pos"),
        CheckConstraint("cost_per_unit >= 0", name="ck_dc_route_cost_nonneg"),
        Index("ix_dc_routes_source_target", "source_dc_id", "target_dc_id"),
    )
