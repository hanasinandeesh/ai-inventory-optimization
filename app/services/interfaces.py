"""
Application Service Interfaces module.
Pure Abstract Protocols for repository capabilities used by Application Services.
Contains ZERO imports from app.infrastructure or SQLAlchemy.
"""

from datetime import date
from typing import Any, Protocol, runtime_checkable

from app.services.dtos import (
    AIRecommendationInputDTO,
    AIRecommendationOutputDTO,
    AuditEventCreateData,
    AuditEventDTO,
    DailyDemandSignalDTO,
    DCRouteDTO,
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
from app.services.unit_of_work import UnitOfWorkProtocol


class ProductRepositoryInterface(Protocol):
    """Protocol for product catalog queries."""

    def get_by_id(self, product_id: int) -> ProductDTO | None: ...

    def get_by_sku(self, sku: str) -> ProductDTO | None: ...


class InventoryRepositoryInterface(Protocol):
    """Protocol for inventory balance queries."""

    def get_balance(self, dc_id: int, product_id: int) -> InventoryBalanceDTO | None: ...


class DemandRepositoryInterface(Protocol):
    """Protocol for daily demand signal queries."""

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ) -> list[DailyDemandSignalDTO]: ...


class InventoryPolicyRepositoryInterface(Protocol):
    """Protocol for SKU/DC inventory policy queries."""

    def get_active_policy(self, dc_id: int, product_id: int) -> InventoryPolicyDTO | None: ...


class DistributionCenterRepositoryInterface(Protocol):
    """Protocol for distribution center queries."""

    def get_by_id(self, dc_id: int) -> DistributionCenterDTO | None: ...

    def get_by_code(self, code: str) -> DistributionCenterDTO | None: ...

    def get_active_source_dcs(self, exclude_dc_id: int) -> list[DistributionCenterDTO]: ...


class RouteRepositoryInterface(Protocol):
    """Protocol for transportation route queries."""

    def get_active_route(self, source_dc_id: int, target_dc_id: int) -> DCRouteDTO | None: ...


class RiskIncidentRepositoryInterface(Protocol):
    """Protocol for stockout risk incident persistence and querying."""

    def find_existing_incident(
        self, target_dc_id: int, product_id: int, status: str = "OPEN"
    ) -> RiskIncidentDTO | None: ...

    def create_incident(self, incident_data: RiskIncidentCreateData) -> RiskIncidentDTO: ...

    def update_incident(
        self, incident_id: int, update_data: RiskIncidentUpdateData
    ) -> RiskIncidentDTO | None: ...

    def get_by_id(self, incident_id: int) -> RiskIncidentDTO | Any | None: ...

    def get_by_code(self, incident_code: str) -> RiskIncidentDTO | Any | None: ...

    def list_incidents(self) -> list[RiskIncidentDTO]: ...

    def update_status(self, incident_id: int, status: str) -> bool: ...


class TransferRecommendationRepositoryInterface(Protocol):
    """Protocol for transfer recommendation persistence and querying."""

    def create_recommendation(
        self, create_data: TransferRecommendationCreateData
    ) -> TransferRecommendationDTO: ...

    def get_by_id(self, recommendation_id: int) -> TransferRecommendationDTO | None: ...

    def get_by_code(self, recommendation_code: str) -> TransferRecommendationDTO | None: ...

    def get_by_incident_id(self, incident_id: int) -> list[TransferRecommendationDTO]: ...

    def update_decision_status(
        self,
        recommendation_id: int,
        new_status: str,
        allowed_current_statuses: tuple[str, ...] = ("PROPOSED", "VALIDATED"),
    ) -> int: ...


class AuditRepositoryInterface(Protocol):
    """Protocol for append-only audit event logging and retrieval."""

    def create_audit_event(self, audit_data: AuditEventCreateData) -> AuditEventDTO: ...

    def get_by_incident_id(self, incident_id: int) -> list[AuditEventDTO]: ...

    def get_by_recommendation_id(self, recommendation_id: int) -> list[AuditEventDTO]: ...


@runtime_checkable
class AIRecommendationProviderInterface(Protocol):
    """Protocol for external AI recommendation providers."""

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO: ...


__all__ = [
    "AIRecommendationProviderInterface",
    "AuditRepositoryInterface",
    "DemandRepositoryInterface",
    "DistributionCenterRepositoryInterface",
    "InventoryPolicyRepositoryInterface",
    "InventoryRepositoryInterface",
    "ProductRepositoryInterface",
    "RiskIncidentRepositoryInterface",
    "RouteRepositoryInterface",
    "TransferRecommendationRepositoryInterface",
    "UnitOfWorkProtocol",
]
