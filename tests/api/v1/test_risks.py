"""
API endpoint integration tests for GET /api/v1/risks and GET /api/v1/risks/{incident_id}.
Verifies Golden Scenario retrieval, ordering, empty DB state, 404 handling, correlation ID,
error mapping, schema validation, and dependency injection.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.db.models.distribution_center import DistributionCenter
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database


def test_list_risks_empty_database(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks returns an empty list when DB has 0 incidents."""
    response = client.get("/api/v1/risks")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == []


def test_list_risks_success(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks returns list of persisted risk incidents."""
    seed_database(test_db, reset=True)

    # Trigger a risk detection to persist an incident
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    assert trigger_res.status_code == status.HTTP_200_OK

    response = client.get("/api/v1/risks")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data) == 1
    inc = data[0]
    assert inc["target_dc_code"] == "DC-CHI"
    assert inc["sku"] == "SKU-8842"
    assert inc["current_dos"] == 2.5
    assert inc["days_to_stockout"] == 2.5
    assert inc["shortage_qty"] == 180.0
    assert inc["severity"] == "CRITICAL"
    assert inc["status"] == "OPEN"
    assert inc["projected_stockout_date"] == "2026-09-18"


def test_get_risk_by_id_success(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks/{incident_id} retrieves a specific risk incident."""
    seed_database(test_db, reset=True)

    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    assert trigger_res.status_code == status.HTTP_200_OK
    created_id = trigger_res.json()["id"]

    response = client.get(f"/api/v1/risks/{created_id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["id"] == created_id
    assert data["target_dc_code"] == "DC-CHI"
    assert data["sku"] == "SKU-8842"
    assert data["current_dos"] == 2.5
    assert data["days_to_stockout"] == 2.5
    assert data["shortage_qty"] == 180.0
    assert data["severity"] == "CRITICAL"
    assert data["status"] == "OPEN"
    assert data["projected_stockout_date"] == "2026-09-18"


def test_get_risk_by_id_not_found(client: TestClient) -> None:
    """Verify GET /api/v1/risks/{incident_id} returns 404 RESOURCE_NOT_FOUND for unknown ID."""
    response = client.get("/api/v1/risks/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "RESOURCE_NOT_FOUND"
    assert "999999" in data["message"]
    assert "correlation_id" in data


def test_list_risks_ordering_newest_first(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks returns incidents ordered deterministically by detected_at DESC."""
    dc = DistributionCenter(code="DC-TEST-ORD", name="Test DC", city="Chicago", state="IL")
    product1 = Product(sku="SKU-ORD-1", name="Product 1", category="Cat", unit_of_measure="EA")
    product2 = Product(sku="SKU-ORD-2", name="Product 2", category="Cat", unit_of_measure="EA")
    test_db.add_all([dc, product1, product2])
    test_db.commit()

    now = datetime.now(UTC)
    old_inc = RiskIncident(
        incident_code="INC-OLD",
        target_dc_id=dc.id,
        product_id=product1.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=50.0,
        severity="HIGH",
        status="OPEN",
        detected_at=now - timedelta(hours=2),
    )
    new_inc = RiskIncident(
        incident_code="INC-NEW",
        target_dc_id=dc.id,
        product_id=product2.id,
        current_dos=2.0,
        days_to_stockout=2.0,
        projected_stockout_date=date(2026, 9, 18),
        shortage_qty=100.0,
        severity="CRITICAL",
        status="OPEN",
        detected_at=now,
    )
    test_db.add_all([old_inc, new_inc])
    test_db.commit()

    response = client.get("/api/v1/risks")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data) >= 2
    # Verify newest incident comes first
    codes = [item["incident_code"] for item in data]
    assert codes[0] == "INC-NEW"
    assert codes[1] == "INC-OLD"


def test_golden_scenario_risk_query_flow(client: TestClient, test_db: Session) -> None:
    """Golden Scenario: trigger risk detection then verify risk list and single retrieval."""
    seed_database(test_db, reset=True)

    # 1. Trigger risk detection
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    assert trigger_res.status_code == status.HTTP_200_OK
    incident_data = trigger_res.json()
    incident_id = incident_data["id"]

    # 2. Query list risks
    list_res = client.get("/api/v1/risks")
    assert list_res.status_code == status.HTTP_200_OK
    list_data = list_res.json()
    found = [r for r in list_data if r["id"] == incident_id]
    assert len(found) == 1
    assert found[0]["target_dc_code"] == "DC-CHI"
    assert found[0]["sku"] == "SKU-8842"
    assert found[0]["current_dos"] == 2.5
    assert found[0]["days_to_stockout"] == 2.5
    assert found[0]["shortage_qty"] == 180.0
    assert found[0]["severity"] == "CRITICAL"

    # 3. Query single risk
    get_res = client.get(f"/api/v1/risks/{incident_id}")
    assert get_res.status_code == status.HTTP_200_OK
    get_data = get_res.json()
    assert get_data["id"] == incident_id
    assert get_data["incident_code"] == incident_data["incident_code"]
    assert get_data["target_dc_code"] == "DC-CHI"
    assert get_data["sku"] == "SKU-8842"


def test_risk_query_response_no_orm_internals(client: TestClient, test_db: Session) -> None:
    """Verify query endpoint returns clean RiskIncidentResponse and no internal ORM attributes."""
    seed_database(test_db, reset=True)
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    created_id = trigger_res.json()["id"]

    response = client.get(f"/api/v1/risks/{created_id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

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
    assert "target_dc_id" not in data
    assert "product_id" not in data
    assert "_sa_instance_state" not in data


def test_risk_query_correlation_id(client: TestClient, test_db: Session) -> None:
    """Verify X-Correlation-ID header is echoed back on risk query endpoints."""
    custom_id = "corr-risk-query-987"
    response = client.get("/api/v1/risks", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Correlation-ID") == custom_id

    error_response = client.get("/api/v1/risks/999999", headers={"X-Correlation-ID": custom_id})
    assert error_response.status_code == status.HTTP_404_NOT_FOUND
    assert error_response.headers.get("X-Correlation-ID") == custom_id
    assert error_response.json()["correlation_id"] == custom_id
