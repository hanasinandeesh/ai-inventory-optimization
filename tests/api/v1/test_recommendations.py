"""
API endpoint integration tests for POST /api/v1/risks/{incident_id}/recommendations.
Verifies Golden Scenario recommendation generation, no-feasible-source handling,
Gemini success, deterministic fallback on AI exception, malformed AI response handling,
post-validation failure guardrails (422), correlation ID tracing, and 404 / 422 error contracts.
"""

from datetime import date
from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_ai_recommendation_provider
from app.infrastructure.db.models.distribution_center import DistributionCenter
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database
from app.main import app
from app.services.dtos import AIRecommendationInputDTO, AIRecommendationOutputDTO


class FakeAIProvider:
    """Fake AI Provider returning a valid selected candidate."""

    def __init__(self, selected_candidate_id: str = "CAND-DC-IND-DC-CHI") -> None:
        self.selected_candidate_id = selected_candidate_id
        self.captured_input: AIRecommendationInputDTO | None = None

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.captured_input = input_data
        return AIRecommendationOutputDTO(
            selected_candidate_id=self.selected_candidate_id,
            rationale="Selected based on lead time and cost efficiency.",
        )


class FailingAIProvider:
    """Fake AI Provider simulating timeout or external API failure."""

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        raise TimeoutError("Gemini API connection timed out")


def test_trigger_recommendation_golden_scenario(client: TestClient, test_db: Session) -> None:
    """Golden Scenario: POST /api/v1/risks/{id}/recommendations for Chicago stockout risk."""
    seed_database(test_db, reset=True)

    # 1. Trigger risk detection to obtain OPEN RiskIncident
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"},
    )
    assert risk_res.status_code == status.HTTP_200_OK
    incident_id = risk_res.json()["id"]

    # 2. Trigger recommendation generation with fake AI provider override
    fake_ai = FakeAIProvider(selected_candidate_id="CAND-DC-IND-DC-CHI")
    app.dependency_overrides[get_ai_recommendation_provider] = lambda: fake_ai

    try:
        response = client.post(f"/api/v1/risks/{incident_id}/recommendations")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["has_recommendation"] is True
        assert data["status"] == "PROPOSED"
        assert data["incident_id"] == incident_id
        assert data["source_dc_code"] == "DC-IND"
        assert data["target_dc_code"] == "DC-CHI"
        assert data["product_sku"] == "SKU-8842"
        assert data["recommended_qty"] == 180
        assert data["estimated_total_cost"] == 450.0
        assert data["recommendation_source"] == "AI"
        assert "Indianapolis selected" in data["rationale"] or "lead time" in data["rationale"]
        assert "recommendation_code" in data
        assert "recommendation_id" in data
    finally:
        app.dependency_overrides.clear()


def test_trigger_recommendation_no_feasible_source(client: TestClient, test_db: Session) -> None:
    """Verify endpoint returns 200 OK with has_recommendation=False when 0 candidates exist."""

    # Setup single DC and product with no other source DCs available
    dc = DistributionCenter(code="DC-SOLO", name="Solo DC", city="Chicago", state="IL")
    product = Product(sku="SKU-SOLO", name="Solo Product", category="Cat", unit_of_measure="EA")
    test_db.add_all([dc, product])
    test_db.commit()

    inc = RiskIncident(
        incident_code="INC-SOLO-001",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=100.0,
        severity="CRITICAL",
        status="OPEN",
    )
    test_db.add(inc)
    test_db.commit()

    response = client.post(f"/api/v1/risks/{inc.id}/recommendations")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["has_recommendation"] is False
    assert data["status"] == "NO_FEASIBLE_SOURCE"
    assert data["recommendation_id"] is None

    assert data["source_dc_code"] is None


def test_trigger_recommendation_gemini_success(client: TestClient, test_db: Session) -> None:
    """Verify AI provider integration succeeds and returns recommendation source as AI."""
    seed_database(test_db, reset=True)
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"},
    )
    incident_id = risk_res.json()["id"]

    fake_ai = FakeAIProvider(selected_candidate_id="CAND-DC-IND-DC-CHI")
    app.dependency_overrides[get_ai_recommendation_provider] = lambda: fake_ai

    try:
        response = client.post(f"/api/v1/risks/{incident_id}/recommendations")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["has_recommendation"] is True
        assert data["recommendation_source"] == "AI"
    finally:
        app.dependency_overrides.clear()


def test_trigger_recommendation_deterministic_fallback_on_ai_exception(
    client: TestClient, test_db: Session
) -> None:
    """Verify AI exception (timeout) triggers deterministic fallback without crashing."""
    seed_database(test_db, reset=True)
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"},
    )
    incident_id = risk_res.json()["id"]

    failing_ai = FailingAIProvider()
    app.dependency_overrides[get_ai_recommendation_provider] = lambda: failing_ai

    try:
        response = client.post(f"/api/v1/risks/{incident_id}/recommendations")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["has_recommendation"] is True
        assert data["status"] == "PROPOSED"
        assert data["source_dc_code"] == "DC-IND"
        assert data["recommendation_source"] == "DETERMINISTIC_FALLBACK"
        assert "DETERMINISTIC_FALLBACK" in data["rationale"]

    finally:
        app.dependency_overrides.clear()


def test_trigger_recommendation_malformed_unknown_ai_candidate(
    client: TestClient, test_db: Session
) -> None:
    """Verify AI returning unknown candidate ID triggers deterministic fallback."""
    seed_database(test_db, reset=True)
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"},
    )
    incident_id = risk_res.json()["id"]

    # AI returns non-existent candidate ID
    malformed_ai = FakeAIProvider(selected_candidate_id="CAND-UNKNOWN-DC")
    app.dependency_overrides[get_ai_recommendation_provider] = lambda: malformed_ai

    try:
        response = client.post(f"/api/v1/risks/{incident_id}/recommendations")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["has_recommendation"] is True
        assert data["status"] == "PROPOSED"
        assert data["source_dc_code"] == "DC-IND"
        assert data["recommendation_source"] == "DETERMINISTIC_FALLBACK"
    finally:
        app.dependency_overrides.clear()


def test_trigger_recommendation_post_validation_failure(
    client: TestClient, test_db: Session
) -> None:
    """Verify post-validation guardrail failure raises 422 RECOMMENDATION_VALIDATION_FAILED."""
    seed_database(test_db, reset=True)
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"},
    )
    incident_id = risk_res.json()["id"]

    # Patch validate_recommendation_proposal to simulate a post-validation guardrail failure
    with patch(
        "app.services.recommendation_service.validate_recommendation_proposal"
    ) as mock_validate:
        from app.domain.exceptions import RecommendationValidationError

        mock_validate.side_effect = RecommendationValidationError(
            "Recommended quantity exceeds surplus"
        )

        response = client.post(f"/api/v1/risks/{incident_id}/recommendations")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()

        assert data["error_code"] == "RECOMMENDATION_VALIDATION_FAILED"
        assert "Recommended quantity exceeds surplus" in data["message"]


def test_trigger_recommendation_unknown_incident_404(client: TestClient) -> None:
    """Verify 404 RESOURCE_NOT_FOUND returned when incident ID does not exist."""
    response = client.post("/api/v1/risks/999999/recommendations")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "RESOURCE_NOT_FOUND"


def test_trigger_recommendation_inactive_incident_422(client: TestClient, test_db: Session) -> None:
    """Verify 422 RESOURCE_INACTIVE returned when incident is not in OPEN status."""
    dc = DistributionCenter(code="DC-INACT", name="Inactive DC", city="City", state="ST")
    product = Product(sku="SKU-INACT", name="Product", category="Cat", unit_of_measure="EA")
    test_db.add_all([dc, product])
    test_db.commit()

    inc = RiskIncident(
        incident_code="INC-RESOLVED-001",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=50.0,
        severity="HIGH",
        status="RESOLVED",  # Non-OPEN status
    )
    test_db.add(inc)
    test_db.commit()

    response = client.post(f"/api/v1/risks/{inc.id}/recommendations")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert data["error_code"] == "RESOURCE_INACTIVE"


def test_trigger_recommendation_correlation_id(client: TestClient, test_db: Session) -> None:
    """Verify X-Correlation-ID header tracing on recommendation endpoint."""
    seed_database(test_db, reset=True)
    risk_res = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-CHI", "sku": "SKU-8842"},
    )
    incident_id = risk_res.json()["id"]

    custom_id = "test-rec-corr-id-99"
    fake_ai = FakeAIProvider()
    app.dependency_overrides[get_ai_recommendation_provider] = lambda: fake_ai

    try:
        response = client.post(
            f"/api/v1/risks/{incident_id}/recommendations",
            headers={"X-Correlation-ID": custom_id},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.headers.get("X-Correlation-ID") == custom_id
    finally:
        app.dependency_overrides.clear()
