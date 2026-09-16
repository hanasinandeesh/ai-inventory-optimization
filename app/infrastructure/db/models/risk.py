from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.audit import AuditEvent
    from app.infrastructure.db.models.distribution_center import DistributionCenter
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.recommendation import TransferRecommendation


class RiskIncident(Base):
    """RiskIncident entity representing a detected stockout risk event."""

    __tablename__ = "risk_incidents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    target_dc_id: Mapped[int] = mapped_column(
        ForeignKey("distribution_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_dos: Mapped[float] = mapped_column(Float, nullable=False)
    days_to_stockout: Mapped[float] = mapped_column(Float, nullable=False)
    projected_stockout_date: Mapped[date] = mapped_column(Date, nullable=False)
    shortage_qty: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    target_dc: Mapped["DistributionCenter"] = relationship(back_populates="risk_incidents")
    product: Mapped["Product"] = relationship(back_populates="risk_incidents")
    recommendations: Mapped[list["TransferRecommendation"]] = relationship(
        back_populates="risk_incident"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="risk_incident")

    __table_args__ = (
        Index(
            "ix_risk_incidents_target_prod_status_sev",
            "target_dc_id",
            "product_id",
            "status",
            "severity",
        ),
    )
