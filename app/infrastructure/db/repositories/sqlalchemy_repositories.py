"""
SQLAlchemy repository implementations.
Converts between SQLAlchemy ORM database models and Application DTOs.
Repositories execute database queries, add/flush to session, but NEVER commit or rollback.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.services.dtos import (
    AuditEventCreateData,
    AuditEventDTO,
    DailyDemandSignalDTO,
    DistributionCenterDTO,
    InventoryBalanceDTO,
    InventoryPolicyDTO,
    ProductDTO,
    RiskIncidentCreateData,
    RiskIncidentDTO,
    RiskIncidentUpdateData,
    TransferRecommendationCreateData,
    TransferRecommendationDTO,
)


class SQLAlchemyProductRepository:
    """SQLAlchemy implementation of ProductRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, product_id: int) -> ProductDTO | None:
        stmt = select(Product).where(Product.id == product_id)
        p = self._session.execute(stmt).scalar_one_or_none()
        if p is None:
            return None
        return ProductDTO(
            id=p.id,
            sku=p.sku,
            name=p.name,
            category=p.category,
            unit_of_measure=p.unit_of_measure,
            pack_size=p.pack_size,
        )

    def get_by_sku(self, sku: str) -> ProductDTO | None:
        stmt = select(Product).where(Product.sku == sku)
        p = self._session.execute(stmt).scalar_one_or_none()
        if p is None:
            return None
        return ProductDTO(
            id=p.id,
            sku=p.sku,
            name=p.name,
            category=p.category,
            unit_of_measure=p.unit_of_measure,
            pack_size=p.pack_size,
        )


class SQLAlchemyInventoryRepository:
    """SQLAlchemy implementation of InventoryRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_balance(self, dc_id: int, product_id: int) -> InventoryBalanceDTO | None:
        stmt = select(InventoryBalance).where(
            InventoryBalance.dc_id == dc_id,
            InventoryBalance.product_id == product_id,
        )
        b = self._session.execute(stmt).scalar_one_or_none()
        if b is None:
            return None
        return InventoryBalanceDTO(
            id=b.id,
            dc_id=b.dc_id,
            product_id=b.product_id,
            on_hand_qty=b.on_hand_qty,
            reserved_qty=b.reserved_qty,
        )


class SQLAlchemyDemandRepository:
    """SQLAlchemy implementation of DemandRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ) -> list[DailyDemandSignalDTO]:
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
        return [
            DailyDemandSignalDTO(
                id=d.id,
                dc_id=d.dc_id,
                product_id=d.product_id,
                signal_date=d.signal_date,
                daily_demand_qty=d.daily_demand_qty,
            )
            for d in result
        ]


class SQLAlchemyInventoryPolicyRepository:
    """SQLAlchemy implementation of InventoryPolicyRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_policy(self, dc_id: int, product_id: int) -> InventoryPolicyDTO | None:
        stmt = select(InventoryPolicy).where(
            InventoryPolicy.dc_id == dc_id,
            InventoryPolicy.product_id == product_id,
            InventoryPolicy.is_active == True,  # noqa: E712
        )
        p = self._session.execute(stmt).scalar_one_or_none()
        if p is None:
            return None
        return InventoryPolicyDTO(
            id=p.id,
            dc_id=p.dc_id,
            product_id=p.product_id,
            safety_stock_days=p.safety_stock_days,
            min_reorder_qty=p.min_reorder_qty,
            is_active=p.is_active,
        )


class SQLAlchemyDistributionCenterRepository:
    """SQLAlchemy implementation of DistributionCenterRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, dc_id: int) -> DistributionCenterDTO | None:
        stmt = select(DistributionCenter).where(DistributionCenter.id == dc_id)
        dc = self._session.execute(stmt).scalar_one_or_none()
        if dc is None:
            return None
        return DistributionCenterDTO(
            id=dc.id,
            code=dc.code,
            name=dc.name,
            city=dc.city,
            state=dc.state,
            is_active=dc.is_active,
        )

    def get_by_code(self, code: str) -> DistributionCenterDTO | None:
        stmt = select(DistributionCenter).where(DistributionCenter.code == code)
        dc = self._session.execute(stmt).scalar_one_or_none()
        if dc is None:
            return None
        return DistributionCenterDTO(
            id=dc.id,
            code=dc.code,
            name=dc.name,
            city=dc.city,
            state=dc.state,
            is_active=dc.is_active,
        )

    def get_active_source_dcs(self, exclude_dc_id: int) -> list[DistributionCenterDTO]:
        stmt = select(DistributionCenter).where(
            DistributionCenter.id != exclude_dc_id,
            DistributionCenter.is_active == True,  # noqa: E712
        )
        result: Sequence[DistributionCenter] = self._session.execute(stmt).scalars().all()
        return [
            DistributionCenterDTO(
                id=dc.id,
                code=dc.code,
                name=dc.name,
                city=dc.city,
                state=dc.state,
                is_active=dc.is_active,
            )
            for dc in result
        ]


class SQLAlchemyRouteRepository:
    """SQLAlchemy implementation of RouteRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_route(self, source_dc_id: int, target_dc_id: int) -> DCRoute | None:
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
    ) -> RiskIncidentDTO | None:
        stmt = select(RiskIncident).where(
            RiskIncident.target_dc_id == target_dc_id,
            RiskIncident.product_id == product_id,
            RiskIncident.status == status,
        )
        inc = self._session.execute(stmt).scalar_one_or_none()
        if inc is None:
            return None
        return RiskIncidentDTO(
            id=inc.id,
            incident_code=inc.incident_code,
            target_dc_id=inc.target_dc_id,
            product_id=inc.product_id,
            current_dos=inc.current_dos,
            days_to_stockout=inc.days_to_stockout,
            projected_stockout_date=inc.projected_stockout_date,
            shortage_qty=inc.shortage_qty,
            severity=inc.severity,
            status=inc.status,
            detected_at=inc.detected_at,
        )

    def create_incident(
        self, incident: RiskIncident | RiskIncidentCreateData
    ) -> RiskIncidentDTO | RiskIncident:
        if isinstance(incident, RiskIncidentCreateData):
            kwargs = {
                "incident_code": incident.incident_code,
                "target_dc_id": incident.target_dc_id,
                "product_id": incident.product_id,
                "current_dos": incident.current_dos,
                "days_to_stockout": incident.days_to_stockout,
                "projected_stockout_date": incident.projected_stockout_date,
                "shortage_qty": incident.shortage_qty,
                "severity": incident.severity,
                "status": incident.status,
            }
            if incident.detected_at is not None:
                kwargs["detected_at"] = incident.detected_at

            orm_inc = RiskIncident(**kwargs)
            self._session.add(orm_inc)
            self._session.flush()
            self._session.refresh(orm_inc)

            return RiskIncidentDTO(
                id=orm_inc.id,
                incident_code=orm_inc.incident_code,
                target_dc_id=orm_inc.target_dc_id,
                product_id=orm_inc.product_id,
                current_dos=orm_inc.current_dos,
                days_to_stockout=orm_inc.days_to_stockout,
                projected_stockout_date=orm_inc.projected_stockout_date,
                shortage_qty=orm_inc.shortage_qty,
                severity=orm_inc.severity,
                status=orm_inc.status,
                detected_at=orm_inc.detected_at,
            )
        self._session.add(incident)
        self._session.flush()
        return incident

    def update_incident(
        self, incident_id: int, update_data: RiskIncidentUpdateData
    ) -> RiskIncidentDTO | None:
        stmt = select(RiskIncident).where(RiskIncident.id == incident_id)
        orm_inc = self._session.execute(stmt).scalar_one_or_none()
        if orm_inc is None:
            return None
        orm_inc.current_dos = update_data.current_dos
        orm_inc.days_to_stockout = update_data.days_to_stockout
        orm_inc.projected_stockout_date = update_data.projected_stockout_date
        orm_inc.shortage_qty = update_data.shortage_qty
        orm_inc.severity = update_data.severity
        self._session.flush()
        return RiskIncidentDTO(
            id=orm_inc.id,
            incident_code=orm_inc.incident_code,
            target_dc_id=orm_inc.target_dc_id,
            product_id=orm_inc.product_id,
            current_dos=orm_inc.current_dos,
            days_to_stockout=orm_inc.days_to_stockout,
            projected_stockout_date=orm_inc.projected_stockout_date,
            shortage_qty=orm_inc.shortage_qty,
            severity=orm_inc.severity,
            status=orm_inc.status,
            detected_at=orm_inc.detected_at,
        )

    def get_by_id(self, incident_id: int) -> RiskIncident | None:
        stmt = select(RiskIncident).where(RiskIncident.id == incident_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, incident_code: str) -> RiskIncident | None:
        stmt = select(RiskIncident).where(RiskIncident.incident_code == incident_code)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_incidents(self) -> list[RiskIncidentDTO]:
        stmt = select(RiskIncident).order_by(RiskIncident.detected_at.desc())
        result: Sequence[RiskIncident] = self._session.execute(stmt).scalars().all()
        return [
            RiskIncidentDTO(
                id=inc.id,
                incident_code=inc.incident_code,
                target_dc_id=inc.target_dc_id,
                product_id=inc.product_id,
                current_dos=inc.current_dos,
                days_to_stockout=inc.days_to_stockout,
                projected_stockout_date=inc.projected_stockout_date,
                shortage_qty=inc.shortage_qty,
                severity=inc.severity,
                status=inc.status,
                detected_at=inc.detected_at,
            )
            for inc in result
        ]

    def update_status(self, incident_id: int, status: str) -> bool:
        stmt = update(RiskIncident).where(RiskIncident.id == incident_id).values(status=status)
        result = self._session.execute(stmt)
        return result.rowcount > 0


class SQLAlchemyTransferRecommendationRepository:
    """SQLAlchemy implementation of TransferRecommendationRepositoryInterface."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_recommendation(
        self, recommendation: TransferRecommendation | TransferRecommendationCreateData
    ) -> TransferRecommendation | TransferRecommendationDTO:
        if isinstance(recommendation, TransferRecommendationCreateData):
            orm_rec = TransferRecommendation(
                recommendation_code=recommendation.recommendation_code,
                incident_id=recommendation.incident_id,
                source_dc_id=recommendation.source_dc_id,
                target_dc_id=recommendation.target_dc_id,
                product_id=recommendation.product_id,
                recommended_qty=recommendation.recommended_qty,
                feasible_qty_snapshot=recommendation.feasible_qty_snapshot,
                source_surplus_snapshot=recommendation.source_surplus_snapshot,
                transit_days_snapshot=recommendation.transit_days_snapshot,
                route_unit_cost_snapshot=recommendation.route_unit_cost_snapshot,
                estimated_cost_snapshot=recommendation.estimated_cost_snapshot,
                rationale=recommendation.rationale,
                recommendation_source=recommendation.recommendation_source,
                status=recommendation.status,
            )
            self._session.add(orm_rec)
            self._session.flush()
            return TransferRecommendationDTO(
                id=orm_rec.id,
                recommendation_code=orm_rec.recommendation_code,
                incident_id=orm_rec.incident_id,
                source_dc_id=orm_rec.source_dc_id,
                target_dc_id=orm_rec.target_dc_id,
                product_id=orm_rec.product_id,
                recommended_qty=orm_rec.recommended_qty,
                feasible_qty_snapshot=orm_rec.feasible_qty_snapshot,
                source_surplus_snapshot=orm_rec.source_surplus_snapshot,
                transit_days_snapshot=orm_rec.transit_days_snapshot,
                route_unit_cost_snapshot=orm_rec.route_unit_cost_snapshot,
                estimated_cost_snapshot=orm_rec.estimated_cost_snapshot,
                rationale=orm_rec.rationale,
                recommendation_source=orm_rec.recommendation_source,
                status=orm_rec.status,
                created_at=orm_rec.created_at,
            )
        self._session.add(recommendation)
        self._session.flush()
        return recommendation

    def get_by_id(self, recommendation_id: int) -> TransferRecommendation | None:
        stmt = select(TransferRecommendation).where(TransferRecommendation.id == recommendation_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, recommendation_code: str) -> TransferRecommendation | None:
        stmt = select(TransferRecommendation).where(
            TransferRecommendation.recommendation_code == recommendation_code
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_incident_id(self, incident_id: int) -> list[TransferRecommendation]:
        stmt = (
            select(TransferRecommendation)
            .where(TransferRecommendation.incident_id == incident_id)
            .order_by(TransferRecommendation.created_at.asc())
        )
        result: Sequence[TransferRecommendation] = self._session.execute(stmt).scalars().all()
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

    def create_audit_event(
        self, audit_event: AuditEvent | AuditEventCreateData
    ) -> AuditEvent | AuditEventDTO:
        if isinstance(audit_event, AuditEventCreateData):
            orm_audit = AuditEvent(
                incident_id=audit_event.incident_id,
                recommendation_id=audit_event.recommendation_id,
                planner_id=audit_event.planner_id,
                action=audit_event.action,
                input_snapshot_json=audit_event.input_snapshot_json,
                final_approved_qty=audit_event.final_approved_qty,
            )
            self._session.add(orm_audit)
            self._session.flush()
            return AuditEventDTO(
                id=orm_audit.id,
                incident_id=orm_audit.incident_id,
                action=orm_audit.action,
                recommendation_id=orm_audit.recommendation_id,
                planner_id=orm_audit.planner_id,
                input_snapshot_json=orm_audit.input_snapshot_json,
                final_approved_qty=orm_audit.final_approved_qty,
                created_at=orm_audit.created_at,
            )
        self._session.add(audit_event)
        self._session.flush()
        return audit_event

    def get_by_incident_id(self, incident_id: int) -> list[AuditEventDTO]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.incident_id == incident_id)
            .order_by(AuditEvent.created_at.asc())
        )
        result: Sequence[AuditEvent] = self._session.execute(stmt).scalars().all()
        return [
            AuditEventDTO(
                id=audit.id,
                incident_id=audit.incident_id,
                action=audit.action,
                recommendation_id=audit.recommendation_id,
                planner_id=audit.planner_id,
                input_snapshot_json=audit.input_snapshot_json,
                final_approved_qty=audit.final_approved_qty,
                created_at=audit.created_at,
            )
            for audit in result
        ]

    def get_by_recommendation_id(self, recommendation_id: int) -> list[AuditEventDTO]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.recommendation_id == recommendation_id)
            .order_by(AuditEvent.created_at.asc())
        )
        result: Sequence[AuditEvent] = self._session.execute(stmt).scalars().all()
        return [
            AuditEventDTO(
                id=audit.id,
                incident_id=audit.incident_id,
                action=audit.action,
                recommendation_id=audit.recommendation_id,
                planner_id=audit.planner_id,
                input_snapshot_json=audit.input_snapshot_json,
                final_approved_qty=audit.final_approved_qty,
                created_at=audit.created_at,
            )
            for audit in result
        ]
