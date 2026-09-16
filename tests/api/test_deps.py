"""
Unit tests for application Composition Root and FastAPI dependencies (app.api.deps).
Verifies dependency construction, settings binding, protocol type adherence, and provider inversion.
"""

from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.api.deps import (
    get_ai_recommendation_provider,
    get_audit_query_service,
    get_candidate_discovery_service,
    get_planner_decision_service,
    get_recommendation_service,
)
from app.core.config import settings
from app.infrastructure.ai.gemini_provider import GeminiRecommendationProvider
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyRiskIncidentRepository,
)
from app.services.audit_query_service import AuditQueryService
from app.services.candidate_discovery_service import CandidateDiscoveryService
from app.services.dtos import AIRecommendationInputDTO, AIRecommendationOutputDTO
from app.services.interfaces import AIRecommendationProviderInterface
from app.services.planner_decision_service import PlannerDecisionService
from app.services.recommendation_service import RecommendationService


class FakeCustomAIProvider:
    """Fake provider implementing AIRecommendationProviderInterface without importing Gemini."""

    def __init__(self) -> None:
        self.captured_input: AIRecommendationInputDTO | None = None

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.captured_input = input_data
        return AIRecommendationOutputDTO(
            selected_candidate_id="CAND-DC-IND-DC-CHI",
            rationale="Fake custom provider selection for dependency inversion test.",
        )


def test_get_ai_recommendation_provider_construction() -> None:
    """Verify get_ai_recommendation_provider constructs Gemini provider from Settings."""
    provider = get_ai_recommendation_provider()

    assert isinstance(provider, GeminiRecommendationProvider)
    assert isinstance(provider, AIRecommendationProviderInterface)
    assert provider._api_key == settings.GEMINI_API_KEY
    assert provider._model_name == settings.GEMINI_MODEL
    assert provider._timeout_seconds == settings.GEMINI_TIMEOUT_SECONDS


def test_get_candidate_discovery_service_construction() -> None:
    """Verify get_candidate_discovery_service constructs discovery service with DB session."""
    mock_db = MagicMock(spec=Session)
    service = get_candidate_discovery_service(db=mock_db)

    assert isinstance(service, CandidateDiscoveryService)


def test_get_recommendation_service_composition() -> None:
    """Verify get_recommendation_service constructs RecommendationService injecting dependencies."""
    mock_db = MagicMock(spec=Session)
    mock_ai_provider = FakeCustomAIProvider()

    service = get_recommendation_service(db=mock_db, ai_provider=mock_ai_provider)

    assert isinstance(service, RecommendationService)
    assert service._ai_provider is mock_ai_provider


def test_recommendation_service_works_with_fake_provider_without_gemini() -> None:
    """Verify RecommendationService operates cleanly with a fake AI provider."""
    fake_provider = FakeCustomAIProvider()
    mock_db = MagicMock(spec=Session)

    service = get_recommendation_service(db=mock_db, ai_provider=fake_provider)

    # Verify RecommendationService is provider-agnostic
    assert service._ai_provider == fake_provider
    assert not hasattr(service, "_gemini_client")


def test_get_planner_decision_service_construction() -> None:
    """Verify get_planner_decision_service constructs PlannerDecisionService
    with expected dependencies."""
    mock_db = MagicMock(spec=Session)

    service = get_planner_decision_service(db=mock_db)

    assert isinstance(service, PlannerDecisionService)
    assert not hasattr(service, "_ai_provider")


def test_get_audit_query_service_construction() -> None:
    """Verify get_audit_query_service constructs AuditQueryService with concrete repositories
    adhering to protocol abstractions and maintaining read-only isolation."""
    mock_db = MagicMock(spec=Session)

    service = get_audit_query_service(db=mock_db)

    # 1. Service constructed successfully
    assert isinstance(service, AuditQueryService)

    # 2. Correct repository implementations injected
    assert isinstance(service._risk_repo, SQLAlchemyRiskIncidentRepository)
    assert isinstance(service._audit_repo, SQLAlchemyAuditRepository)

    # 3. Injected repositories support protocol method contracts
    assert callable(getattr(service._risk_repo, "get_by_id", None))
    assert callable(getattr(service._audit_repo, "get_by_incident_id", None))

    # 4. No transaction/write behavior introduced (no UoW, read-only)
    assert not hasattr(service, "_uow")
    assert not hasattr(service, "_write_repo")
