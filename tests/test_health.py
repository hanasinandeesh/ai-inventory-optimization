from unittest.mock import patch

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError


def test_health_endpoint_success(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data
    assert data["database"] == "connected"


def test_root_health_endpoint_alias(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"


def test_health_endpoint_db_failure(client: TestClient) -> None:
    with patch("app.api.v1.endpoints.health.check_db_connection") as mock_check:
        mock_check.side_effect = SQLAlchemyError("DB Error")
        response = client.get("/api/v1/health")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["detail"]["status"] == "error"
        assert data["detail"]["database"] == "disconnected"
