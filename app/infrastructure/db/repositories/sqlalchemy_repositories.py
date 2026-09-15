from collections.abc import Sequence
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident


class SQLAlchemyInventoryRepository:
    """SQLAlchemy implementation of InventoryRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_balance(
        self, dc_id: int, product_id: int
    ) -> InventoryBalance | None:
        stmt = select(InventoryBalance).where(
            InventoryBalance.dc_id == dc_id,
            InventoryBalance.product_id == product_id,
        )
        return self._session.execute(stmt).scalar_one_or_none()


class SQLAlchemyDemandRepository:
    """SQLAlchemy implementation of DemandRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ) -> list[DailyDemandSignal]:
        stmt = (
            select(DailyDemandSignal)
            .where(
                DailyDemandSignal.dc_id == dc_id,
                DailyDemandSignal.product_id == product_id,
                DailyDemandSignal.signal_date >= start_date,
                DailyDemandSignal.signal_date <= end_date,
            )
            .order_by(DailyDemandSignal.signal_date.asc())
        )
        result: Sequence[DailyDemandSignal] = self._session.execute(stmt).scalars().all()
        return list(result)


class SQLAlchemyInventoryPolicyRepository:
    """SQLAlchemy implementation of InventoryPolicyRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_policy(
        self, dc_id: int, product_id: int
    ) -> InventoryPolicy | None:
        stmt = select(InventoryPolicy).where(
            InventoryPolicy.dc_id == dc_id,
            InventoryPolicy.product_id == product_id,
            InventoryPolicy.is_active == True,  # noqa: E712
        )
        return self._session.execute(stmt).scalar_one_or_none()


class SQLAlchemyDistributionCenterRepository:
    """SQLAlchemy implementation of DistributionCenterRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, dc_id: int) -> DistributionCenter | None:
        stmt = select(DistributionCenter).where(DistributionCenter.id == dc_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> DistributionCenter | None:
        stmt = select(DistributionCenter).where(DistributionCenter.code == code)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_active_source_dcs(
        self, exclude_dc_id: int
    ) -> list[DistributionCenter]:
        stmt = select(DistributionCenter).where(
            DistributionCenter.id != exclude_dc_id,
            DistributionCenter.is_active == True,  # noqa: E712
        )
        result: Sequence[DistributionCenter] = self._session.execute(stmt).scalars().all()
        return list(result)


class SQLAlchemyRouteRepository:
    """SQLAlchemy implementation of RouteRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_route(
        self, source_dc_id: int, target_dc_id: int
    ) -> DCRoute | None:
        stmt = select(DCRoute).where(
            DCRoute.source_dc_id == source_dc_id,
            DCRoute.target_dc_id == target_dc_id,
            DCRoute.is_active == True,  # noqa: E712
        )
        return self._session.execute(stmt).scalar_one_or_none()


class SQLAlchemyRiskIncidentRepository:
    """SQLAlchemy implementation of RiskIncidentRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_existing_incident(
        self, target_dc_id: int, product_id: int, status: str = "OPEN"
    ) -> RiskIncident | None:
        stmt = select(RiskIncident).where(
            RiskIncident.target_dc_id == target_dc_id,
            RiskIncident.product_id == product_id,
            RiskIncident.status == status,
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def create_incident(self, incident: RiskIncident) -> RiskIncident:
        self._session.add(incident)
        self._session.flush()
        return incident

    def get_by_id(self, incident_id: int) -> RiskIncident | None:
        stmt = select(RiskIncident).where(RiskIncident.id == incident_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, incident_code: str) -> RiskIncident | None:
        stmt = select(RiskIncident).where(RiskIncident.incident_code == incident_code)
        return self._session.execute(stmt).scalar_one_or_none()

    def update_status(self, incident_id: int, status: str) -> bool:
        stmt = (
            update(RiskIncident)
            .where(RiskIncident.id == incident_id)
            .values(status=status)
        )
        result = self._session.execute(stmt)
        return result.rowcount > 0


class SQLAlchemyTransferRecommendationRepository:
    """SQLAlchemy implementation of TransferRecommendationRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self, recommendation: TransferRecommendation
    ) -> TransferRecommendation:
        self._session.add(recommendation)
        self._session.flush()
        return recommendation

    def get_by_id(
        self, recommendation_id: int
    ) -> TransferRecommendation | None:
        stmt = select(TransferRecommendation).where(
            TransferRecommendation.id == recommendation_id
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(
        self, recommendation_code: str
    ) -> TransferRecommendation | None:
        stmt = select(TransferRecommendation).where(
            TransferRecommendation.recommendation_code == recommendation_code
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_incident_id(
        self, incident_id: int
    ) -> list[TransferRecommendation]:
        stmt = (
            select(TransferRecommendation)
            .where(TransferRecommendation.incident_id == incident_id)
            .order_by(TransferRecommendation.created_at.asc())
        )
        result: Sequence[TransferRecommendation] = (
            self._session.execute(stmt).scalars().all()
        )
        return list(result)

    def update_decision_status(
        self,
        recommendation_id: int,
        new_status: str,
        allowed_current_statuses: tuple[str, ...] = ("PROPOSED", "VALIDATED"),
    ) -> int:
        stmt = (
            update(TransferRecommendation)
            .where(
                TransferRecommendation.id == recommendation_id,
                TransferRecommendation.status.in_(allowed_current_statuses),
            )
            .values(status=new_status)
        )
        result = self._session.execute(stmt)
        return result.rowcount


class SQLAlchemyAuditRepository:
    """SQLAlchemy implementation of AuditRepositoryInterface. Append-only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_audit_event(self, audit_event: AuditEvent) -> AuditEvent:
        self._session.add(audit_event)
        self._session.flush()
        return audit_event

    def get_by_incident_id(self, incident_id: int) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(AuditEvent.created_at.asc())
        )
        result: Sequence[AuditEvent] = self._session.execute(stmt).scalars().all()
        return list(result)

    def get_by_recommendation_id(
        self, recommendation_id: int
    ) -> list[AuditEvent]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.recommendation_id == recommendation_id)
            .order_by(AuditEvent.created_at.asc())
        )
        result: Sequence[AuditEvent] = self._session.execute(stmt).scalars().all()
        return list(result)
