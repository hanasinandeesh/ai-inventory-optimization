"""
API endpoint integration tests for POST /api/v1/risk-detections.
Verifies Golden Scenario, idempotency, error mapping contracts, schema validation,
correlation ID tracing, and ORM isolation.
"""

from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.db.models.distribution_center import DistributionCenter
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database


def test_trigger_risk_detection_golden_scenario(client: TestClient, test_db: Session) -> None:
    """Golden Scenario: POST /api/v1/risk-detections for DC-CHI and SKU-8842."""
    seed_database(test_db, reset=True)

    payload = {
        "dc_code": "DC-CHI",
        "sku": "SKU-8842",
        "detection_date": "2026-09-16",
    }
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["target_dc_code"] == "DC-CHI"
    assert data["sku"] == "SKU-8842"
    assert data["current_dos"] == 2.5
    assert data["days_to_stockout"] == 2.5
    assert data["projected_stockout_date"] == "2026-09-18"
    assert data["shortage_qty"] == 180.0
    assert data["severity"] == "CRITICAL"
    assert data["status"] == "OPEN"
    assert "id" in data
    assert "incident_code" in data
    assert "detected_at" in data

    # Verify X-Correlation-ID header in response
    assert "X-Correlation-ID" in response.headers


def test_trigger_risk_detection_optional_date(client: TestClient, test_db: Session) -> None:
    """Verify detection_date is optional and defaults cleanly."""
    seed_database(test_db, reset=True)

    payload = {
        "dc_code": "DC-CHI",
        "sku": "SKU-8842",
    }
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["target_dc_code"] == "DC-CHI"
    assert data["status"] == "OPEN"


def test_trigger_risk_detection_missing_dc_code(client: TestClient) -> None:
    """Verify missing dc_code returns 400 with INVALID_REQUEST_BODY."""
    payload = {"sku": "SKU-8842"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error_code"] == "INVALID_REQUEST_BODY"
    assert "message" in data
    assert "details" in data
    assert "correlation_id" in data


def test_trigger_risk_detection_missing_sku(client: TestClient) -> None:
    """Verify missing sku returns 400 with INVALID_REQUEST_BODY."""
    payload = {"dc_code": "DC-CHI"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error_code"] == "INVALID_REQUEST_BODY"
    assert "correlation_id" in data


def test_trigger_risk_detection_invalid_json(client: TestClient) -> None:
    """Verify invalid JSON body payload returns 400 Bad Request."""
    response = client.post(
        "/api/v1/risk-detections",
        content="INVALID_JSON_BODY",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["error_code"] == "INVALID_REQUEST_BODY"


def test_trigger_risk_detection_unknown_dc(client: TestClient, test_db: Session) -> None:
    """Verify non-existent DC returns 404 RESOURCE_NOT_FOUND."""
    seed_database(test_db, reset=True)

    payload = {"dc_code": "DC-UNKNOWN", "sku": "SKU-8842"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "RESOURCE_NOT_FOUND"
    assert "DC-UNKNOWN" in data["message"]
    assert "correlation_id" in data


def test_trigger_risk_detection_unknown_sku(client: TestClient, test_db: Session) -> None:
    """Verify non-existent SKU returns 404 RESOURCE_NOT_FOUND."""
    seed_database(test_db, reset=True)

    payload = {"dc_code": "DC-CHI", "sku": "SKU-UNKNOWN"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "RESOURCE_NOT_FOUND"
    assert "SKU-UNKNOWN" in data["message"]


def test_trigger_risk_detection_inactive_dc(client: TestClient, test_db: Session) -> None:
    """Verify inactive target DC returns 422 RESOURCE_INACTIVE."""
    seed_database(test_db, reset=True)

    dc_chi = test_db.query(DistributionCenter).filter_by(code="DC-CHI").one()
    dc_chi.is_active = False
    test_db.commit()

    payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    data = response.json()
    assert data["error_code"] == "RESOURCE_INACTIVE"
    assert "inactive" in data["message"]


def test_trigger_risk_detection_idempotency(client: TestClient, test_db: Session) -> None:
    """Verify repeated detection calls update existing OPEN incident without creating duplicates."""
    seed_database(test_db, reset=True)

    payload = {
        "dc_code": "DC-CHI",
        "sku": "SKU-8842",
        "detection_date": "2026-09-16",
    }
    res1 = client.post("/api/v1/risk-detections", json=payload)
    assert res1.status_code == status.HTTP_200_OK
    incident_id1 = res1.json()["id"]

    res2 = client.post("/api/v1/risk-detections", json=payload)
    assert res2.status_code == status.HTTP_200_OK
    incident_id2 = res2.json()["id"]

    assert incident_id1 == incident_id2

    # Verify only 1 RiskIncident record exists in DB for DC-CHI and SKU-8842
    open_incidents = test_db.query(RiskIncident).filter_by(status="OPEN").all()
    assert len(open_incidents) == 1


def test_trigger_risk_detection_unhandled_exception() -> None:
    """Verify unhandled internal service exception maps to 500 INTERNAL_SERVER_ERROR."""
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    with patch(
        "app.services.process_risk_detection_service.ProcessRiskDetectionService.process_risk_detection"
    ) as mock_service:
        mock_service.side_effect = RuntimeError("Database connection lost")
        payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}
        response = client.post("/api/v1/risk-detections", json=payload)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert data["error_code"] == "INTERNAL_SERVER_ERROR"
        assert data["message"] == "An unexpected server error occurred"
        # Verify internal exception details are not exposed in message
        assert "Database connection lost" not in data["message"]


def test_trigger_risk_detection_response_no_orm_internals(
    client: TestClient, test_db: Session
) -> None:
    """Verify response strictly adheres to RiskIncidentResponse schema with 0 ORM internals."""
    seed_database(test_db, reset=True)

    payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    response = client.post("/api/v1/risk-detections", json=payload)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Expected exact 11 fields from RiskIncidentResponse
    expected_keys = {
        "id",
        "incident_code",
        "target_dc_code",
        "sku",
        "current_dos",
        "days_to_stockout",
        "projected_stockout_date",
        "shortage_qty",
        "severity",
        "status",
        "detected_at",
    }
    assert set(data.keys()) == expected_keys

    # ORM surrogate IDs (target_dc_id, product_id) must NOT be present
    assert "target_dc_id" not in data
    assert "product_id" not in data
    assert "_sa_instance_state" not in data


def test_trigger_risk_detection_custom_correlation_id(client: TestClient, test_db: Session) -> None:
    """Verify incoming X-Correlation-ID header is echoed back in response and error payloads."""
    seed_database(test_db, reset=True)

    custom_id = "test-corr-id-12345"
    payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}

    # Success path
    response = client.post(
        "/api/v1/risk-detections",
        json=payload,
        headers={"X-Correlation-ID": custom_id},
    )
    assert response.headers.get("X-Correlation-ID") == custom_id

    # Error path
    error_response = client.post(
        "/api/v1/risk-detections",
        json={"dc_code": "DC-UNKNOWN", "sku": "SKU-8842"},
        headers={"X-Correlation-ID": custom_id},
    )
    assert error_response.headers.get("X-Correlation-ID") == custom_id
    assert error_response.json()["correlation_id"] == custom_id
