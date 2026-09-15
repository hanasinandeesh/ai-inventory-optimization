from datetime import date
from typing import Protocol

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DCRoute, DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident


class InventoryRepositoryInterface(Protocol):
    """Protocol for inventory balance queries. Inventory mutations are strictly forbidden."""

    def get_balance(
        self, dc_id: int, product_id: int
    ) -> InventoryBalance | None: ...


class DemandRepositoryInterface(Protocol):
    """Protocol for daily demand signal queries."""

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ) -> list[DailyDemandSignal]: ...


class InventoryPolicyRepositoryInterface(Protocol):
    """Protocol for SKU/DC inventory policy queries."""

    def get_active_policy(
        self, dc_id: int, product_id: int
    ) -> InventoryPolicy | None: ...


class DistributionCenterRepositoryInterface(Protocol):
    """Protocol for distribution center queries."""

    def get_by_id(self, dc_id: int) -> DistributionCenter | None: ...

    def get_by_code(self, code: str) -> DistributionCenter | None: ...

    def get_active_source_dcs(
        self, exclude_dc_id: int
    ) -> list[DistributionCenter]: ...


class RouteRepositoryInterface(Protocol):
    """Protocol for transportation route queries."""

    def get_active_route(
        self, source_dc_id: int, target_dc_id: int
    ) -> DCRoute | None: ...


class RiskIncidentRepositoryInterface(Protocol):
    """Protocol for stockout risk incident persistence and querying."""

    def find_existing_incident(
        self, target_dc_id: int, product_id: int, status: str = "OPEN"
    ) -> RiskIncident | None: ...

    def create_incident(self, incident: RiskIncident) -> RiskIncident: ...

    def get_by_id(self, incident_id: int) -> RiskIncident | None: ...

    def get_by_code(self, incident_code: str) -> RiskIncident | None: ...

    def update_status(self, incident_id: int, status: str) -> bool: ...


class TransferRecommendationRepositoryInterface(Protocol):
    """Protocol for transfer recommendation persistence and conditional decision updates."""

    def create_recommendation(
        self, recommendation: TransferRecommendation
    ) -> TransferRecommendation: ...

    def get_by_id(
        self, recommendation_id: int
    ) -> TransferRecommendation | None: ...

    def get_by_code(
        self, recommendation_code: str
    ) -> TransferRecommendation | None: ...

    def get_by_incident_id(
        self, incident_id: int
    ) -> list[TransferRecommendation]: ...

    def update_decision_status(
        self,
        recommendation_id: int,
        new_status: str,
        allowed_current_statuses: tuple[str, ...] = ("PROPOSED", "VALIDATED"),
    ) -> int: ...


class AuditRepositoryInterface(Protocol):
    """
    Protocol for append-only audit event logging and retrieval.
    Updates/Deletes are strictly forbidden.
    """

    def create_audit_event(self, audit_event: AuditEvent) -> AuditEvent: ...

    def get_by_incident_id(self, incident_id: int) -> list[AuditEvent]: ...

    def get_by_recommendation_id(
        self, recommendation_id: int
    ) -> list[AuditEvent]: ...
