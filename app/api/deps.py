"""
Application Composition Root and FastAPI Dependency Injection Factories.
Constructs concrete infrastructure adapters (SQLAlchemy Repositories, UnitOfWork, Gemini Adapter)
and injects them into pure Application Services via Protocols.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.infrastructure.ai.gemini_provider import GeminiRecommendationProvider
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyProductRepository,
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyRouteRepository,
    SQLAlchemyTransferRecommendationRepository,
)
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.interfaces import AIRecommendationProviderInterface, UnitOfWorkProtocol
from app.services.process_risk_detection_service import ProcessRiskDetectionService
from app.services.recommendation_service import RecommendationService
from app.services.risk_query_service import RiskQueryService


def get_process_risk_detection_service(
    db: Annotated[Session, Depends(get_db)],
) -> ProcessRiskDetectionService:
    """
    Factory constructing ProcessRiskDetectionService with concrete repositories and UnitOfWork.
    """
    return ProcessRiskDetectionService(
        dc_repo=SQLAlchemyDistributionCenterRepository(db),
        product_repo=SQLAlchemyProductRepository(db),
        inventory_repo=SQLAlchemyInventoryRepository(db),
        demand_repo=SQLAlchemyDemandRepository(db),
        policy_repo=SQLAlchemyInventoryPolicyRepository(db),
        risk_repo=SQLAlchemyRiskIncidentRepository(db),
        audit_repo=SQLAlchemyAuditRepository(db),
        uow=SQLAlchemyUnitOfWork(db),
    )


def get_risk_query_service(
    db: Annotated[Session, Depends(get_db)],
) -> RiskQueryService:
    """
    Factory constructing RiskQueryService with concrete repositories.
    """
    return RiskQueryService(
        risk_repo=SQLAlchemyRiskIncidentRepository(db),
        dc_repo=SQLAlchemyDistributionCenterRepository(db),
        product_repo=SQLAlchemyProductRepository(db),
    )


def get_ai_recommendation_provider() -> AIRecommendationProviderInterface:
    """
    Factory creating the concrete AI recommendation provider.
    Constructs GeminiRecommendationProvider using application settings.
    """
    return GeminiRecommendationProvider(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_MODEL,
        timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
    )


def get_unit_of_work(
    db: Annotated[Session, Depends(get_db)],
) -> Generator[UnitOfWorkProtocol, None, None]:
    """Factory providing the SQLAlchemy UnitOfWork for transaction management."""
    yield SQLAlchemyUnitOfWork(db)


def get_candidate_discovery_service(
    db: Annotated[Session, Depends(get_db)],
) -> CandidateDiscoveryService:
    """Factory constructing CandidateDiscoveryService with concrete repositories."""
    return CandidateDiscoveryService(
        risk_repo=SQLAlchemyRiskIncidentRepository(db),
        dc_repo=SQLAlchemyDistributionCenterRepository(db),
        inventory_repo=SQLAlchemyInventoryRepository(db),
        demand_repo=SQLAlchemyDemandRepository(db),
        policy_repo=SQLAlchemyInventoryPolicyRepository(db),
        route_repo=SQLAlchemyRouteRepository(db),
    )


def get_recommendation_service(
    db: Annotated[Session, Depends(get_db)],
    ai_provider: Annotated[
        AIRecommendationProviderInterface, Depends(get_ai_recommendation_provider)
    ],
) -> RecommendationService:
    """
    Composition Root factory constructing RecommendationService.
    Injects repositories, UnitOfWork, discovery service, and AI provider.
    """
    risk_repo = SQLAlchemyRiskIncidentRepository(db)
    dc_repo = SQLAlchemyDistributionCenterRepository(db)
    product_repo = SQLAlchemyProductRepository(db)
    inventory_repo = SQLAlchemyInventoryRepository(db)
    policy_repo = SQLAlchemyInventoryPolicyRepository(db)
    route_repo = SQLAlchemyRouteRepository(db)
    recommendation_repo = SQLAlchemyTransferRecommendationRepository(db)
    audit_repo = SQLAlchemyAuditRepository(db)
    demand_repo = SQLAlchemyDemandRepository(db)

    uow = SQLAlchemyUnitOfWork(db)

    candidate_discovery_service = CandidateDiscoveryService(
        risk_repo=risk_repo,
        dc_repo=dc_repo,
        inventory_repo=inventory_repo,
        demand_repo=demand_repo,
        policy_repo=policy_repo,
        route_repo=route_repo,
    )

    return RecommendationService(
        risk_repo=risk_repo,
        dc_repo=dc_repo,
        product_repo=product_repo,
        inventory_repo=inventory_repo,
        policy_repo=policy_repo,
        route_repo=route_repo,
        recommendation_repo=recommendation_repo,
        audit_repo=audit_repo,
        candidate_discovery_service=candidate_discovery_service,
        ai_provider=ai_provider,
        uow=uow,
        demand_repo=demand_repo,
    )
