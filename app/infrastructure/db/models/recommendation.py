from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.audit import AuditEvent
    from app.infrastructure.db.models.distribution_center import DistributionCenter
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.risk import RiskIncident


class TransferRecommendation(Base):
    """
    TransferRecommendation entity representing proposed inventory rebalancing transfers.
    NOTE: Preserves decision-time snapshot values for auditability and compliance.
    """

    __tablename__ = "transfer_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recommendation_code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("risk_incidents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recommended_qty: Mapped[int] = mapped_column(nullable=False)

    # Immutable Decision-Time Snapshots
    feasible_qty_snapshot: Mapped[int] = mapped_column(nullable=False)
    source_surplus_snapshot: Mapped[int] = mapped_column(nullable=False)
    transit_days_snapshot: Mapped[int] = mapped_column(nullable=False)
    route_unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    estimated_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PROPOSED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    risk_incident: Mapped["RiskIncident"] = relationship(
        back_populates="recommendations"
    )
    source_dc: Mapped["DistributionCenter"] = relationship(
        foreign_keys=[source_dc_id], back_populates="outbound_recommendations"
    )
    target_dc: Mapped["DistributionCenter"] = relationship(
        foreign_keys=[target_dc_id], back_populates="inbound_recommendations"
    )
    product: Mapped["Product"] = relationship(
        back_populates="transfer_recommendations"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="recommendation"
    )

    __table_args__ = (
        CheckConstraint("source_dc_id != target_dc_id", name="ck_rec_diff_dcs"),
        CheckConstraint("recommended_qty > 0", name="ck_rec_qty_pos"),
        Index("ix_transfer_recommendations_incident_source", "incident_id", "source_dc_id"),
    )
