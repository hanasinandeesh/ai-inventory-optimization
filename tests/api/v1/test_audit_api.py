"""
API integration tests for GET /api/v1/risks/{incident_id}/audit.
Verifies audit trail retrieval, empty state, 404 handling, routing, schema adherence,
chronological ordering, correlation ID behavior, read-only guarantees, and OpenAPI schema presence.
"""

from datetime import date, datetime

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.distribution_center import DistributionCenter
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database


def test_get_audit_trail_success_with_events(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks/{incident_id}/audit returns audit events ordered oldest first."""
    seed_database(test_db, reset=True)

    # 1. Trigger risk detection -> creates RISK_DETECTED audit event
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    assert trigger_res.status_code == status.HTTP_200_OK
    incident_id = trigger_res.json()["id"]

    # 2. Trigger recommendation generation -> creates RECOMMENDATION_GENERATED audit event
    rec_res = client.post(f"/api/v1/risks/{incident_id}/recommendations")
    assert rec_res.status_code == status.HTTP_200_OK
    rec_id = rec_res.json()["recommendation_id"]

    # 3. Approve recommendation -> creates PLANNER_APPROVED audit event
    approve_res = client.post(
        f"/api/v1/recommendations/{rec_id}/approve",
        json={"planner_id": "planner_test", "comment": "Audit test approval"},
    )
    assert approve_res.status_code == status.HTTP_200_OK

    # 4. GET audit trail
    response = client.get(f"/api/v1/risks/{incident_id}/audit")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data) == 3
    assert data[0]["action"] == "RISK_DETECTED"
    assert data[1]["action"] == "RECOMMENDATION_GENERATED"
    assert data[2]["action"] == "PLANNER_APPROVED"
    assert data[2]["planner_id"] == "planner_test"
    assert data[2]["final_approved_qty"] == 180

    # Verify chronological ordering (oldest created_at first)
    timestamps = [datetime.fromisoformat(item["created_at"]) for item in data]
    assert timestamps == sorted(timestamps)


def test_get_audit_trail_empty(client: TestClient, test_db: Session) -> None:
    """Verify GET /api/v1/risks/{incident_id}/audit returns empty list when no audit events."""
    dc = DistributionCenter(code="DC-TEST-EMPTY", name="Test DC", city="Chicago", state="IL")
    product = Product(sku="SKU-EMPTY-1", name="Product 1", category="Cat", unit_of_measure="EA")
    test_db.add_all([dc, product])
    test_db.commit()

    incident = RiskIncident(
        incident_code="INC-NO-AUDIT",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 20),
        shortage_qty=50.0,
        severity="HIGH",
        status="OPEN",
    )
    test_db.add(incident)
    test_db.commit()

    response = client.get(f"/api/v1/risks/{incident.id}/audit")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == []


def test_get_audit_trail_nonexistent_incident(client: TestClient) -> None:
    """Verify GET /api/v1/risks/{incident_id}/audit returns 404 for unknown incident."""
    response = client.get("/api/v1/risks/999999/audit")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["error_code"] == "RESOURCE_NOT_FOUND"
    assert "999999" in data["message"]
    assert "correlation_id" in data


def test_get_audit_trail_incident_id_routing(client: TestClient, test_db: Session) -> None:
    """Verify audit trail returns only audit events specific to the requested incident_id."""
    dc = DistributionCenter(code="DC-TEST-ROUTE", name="Test DC", city="Chicago", state="IL")
    product = Product(sku="SKU-ROUTE-1", name="Product 1", category="Cat", unit_of_measure="EA")
    test_db.add_all([dc, product])
    test_db.commit()

    inc1 = RiskIncident(
        incident_code="INC-ROUTE-1",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 20),
        shortage_qty=50.0,
        severity="HIGH",
        status="OPEN",
    )
    inc2 = RiskIncident(
        incident_code="INC-ROUTE-2",
        target_dc_id=dc.id,
        product_id=product.id,
        current_dos=2.0,
        days_to_stockout=2.0,
        projected_stockout_date=date(2026, 9, 21),
        shortage_qty=100.0,
        severity="CRITICAL",
        status="OPEN",
    )
    test_db.add_all([inc1, inc2])
    test_db.commit()

    event1 = AuditEvent(incident_id=inc1.id, action="INCIDENT_1_EVENT")
    event2 = AuditEvent(incident_id=inc2.id, action="INCIDENT_2_EVENT")
    test_db.add_all([event1, event2])
    test_db.commit()

    res1 = client.get(f"/api/v1/risks/{inc1.id}/audit")
    assert res1.status_code == status.HTTP_200_OK
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["action"] == "INCIDENT_1_EVENT"

    res2 = client.get(f"/api/v1/risks/{inc2.id}/audit")
    assert res2.status_code == status.HTTP_200_OK
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["action"] == "INCIDENT_2_EVENT"


def test_get_audit_trail_schema_validation(client: TestClient, test_db: Session) -> None:
    """Verify audit endpoint returns schema matching AuditEventResponse without ORM internals."""
    seed_database(test_db, reset=True)
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842", "detection_date": "2026-09-16"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    incident_id = trigger_res.json()["id"]

    response = client.get(f"/api/v1/risks/{incident_id}/audit")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data) == 1
    item = data[0]
    expected_keys = {
        "id",
        "incident_id",
        "action",
        "recommendation_id",
        "planner_id",
        "input_snapshot_json",
        "final_approved_qty",
        "created_at",
    }
    assert set(item.keys()) == expected_keys
    assert "_sa_instance_state" not in item


def test_get_audit_trail_correlation_id(client: TestClient, test_db: Session) -> None:
    """Verify X-Correlation-ID header is echoed in responses for both 200 and 404."""
    seed_database(test_db, reset=True)
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    incident_id = trigger_res.json()["id"]

    custom_id = "corr-audit-test-999"
    response = client.get(
        f"/api/v1/risks/{incident_id}/audit", headers={"X-Correlation-ID": custom_id}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("X-Correlation-ID") == custom_id

    error_res = client.get("/api/v1/risks/999999/audit", headers={"X-Correlation-ID": custom_id})
    assert error_res.status_code == status.HTTP_404_NOT_FOUND
    assert error_res.headers.get("X-Correlation-ID") == custom_id
    assert error_res.json()["correlation_id"] == custom_id


def test_get_audit_trail_does_not_perform_writes(client: TestClient, test_db: Session) -> None:
    """Verify calling GET /api/v1/risks/{incident_id}/audit performs zero database writes."""
    seed_database(test_db, reset=True)
    trigger_payload = {"dc_code": "DC-CHI", "sku": "SKU-8842"}
    trigger_res = client.post("/api/v1/risk-detections", json=trigger_payload)
    incident_id = trigger_res.json()["id"]

    count_before = test_db.scalar(select(func.count(AuditEvent.id)))
    response = client.get(f"/api/v1/risks/{incident_id}/audit")
    assert response.status_code == status.HTTP_200_OK
    count_after = test_db.scalar(select(func.count(AuditEvent.id)))

    assert count_before == count_after


def test_openapi_schema_contains_audit_endpoint(client: TestClient) -> None:
    """Verify OpenAPI schema includes GET /api/v1/risks/{incident_id}/audit and status responses."""
    schema = client.app.openapi()

    path_key = "/api/v1/risks/{incident_id}/audit"
    assert path_key in schema["paths"]
    get_op = schema["paths"][path_key]["get"]
    assert "200" in get_op["responses"]
    assert "404" in get_op["responses"]
    assert "500" in get_op["responses"]
