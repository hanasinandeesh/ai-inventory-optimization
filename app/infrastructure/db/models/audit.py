from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.recommendation import TransferRecommendation
    from app.infrastructure.db.models.risk import RiskIncident


class AuditEvent(Base):
    """
    AuditEvent entity storing an append-only log of planner decisions and system events.
    Supports system-generated (planner_id=None) and planner-directed actions.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(
        ForeignKey("risk_incidents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("transfer_recommendations.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    planner_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    input_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_approved_qty: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    risk_incident: Mapped["RiskIncident"] = relationship(back_populates="audit_events")
    recommendation: Mapped[Optional["TransferRecommendation"]] = relationship(
        back_populates="audit_events"
    )

    __table_args__ = (
        Index(
            "ix_audit_events_incident_rec_created",
            "incident_id",
            "recommendation_id",
            "created_at",
        ),
    )
