"""
API integration tests for Planner Decision endpoints:
POST /api/v1/recommendations/{recommendation_id}/approve
POST /api/v1/recommendations/{recommendation_id}/reject
"""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.db.models.inventory import InventoryBalance
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.seed.seed import seed_database


def _seed_decision_test_data(db: Session) -> dict[str, int]:
    """Helper seeding an OPEN RiskIncident and two TransferRecommendations."""
    seed_database(db, reset=True)

    incident = RiskIncident(
        incident_code="INC-API-DECISION",
        target_dc_id=1,  # DC-CHI
        product_id=1,  # SKU-8842
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=180,
        severity="CRITICAL",
        status="OPEN",
    )
    db.add(incident)
    db.flush()

    rec_proposed = TransferRecommendation(
        recommendation_code="REC-API-PROP",
        incident_id=incident.id,
        source_dc_id=2,  # DC-IND
        target_dc_id=1,  # DC-CHI
        product_id=1,  # SKU-8842
        recommended_qty=180,
        feasible_qty_snapshot=180,
        source_surplus_snapshot=450,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("2.50"),
        estimated_cost_snapshot=Decimal("450.00"),
        rationale="Proposed transfer",
        recommendation_source="AI",
        status="PROPOSED",
    )
    db.add(rec_proposed)

    rec_validated = TransferRecommendation(
        recommendation_code="REC-API-VAL",
        incident_id=incident.id,
        source_dc_id=2,
        target_dc_id=1,
        product_id=1,
        recommended_qty=180,
        feasible_qty_snapshot=180,
        source_surplus_snapshot=450,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("2.50"),
        estimated_cost_snapshot=Decimal("450.00"),
        rationale="Validated transfer",
        recommendation_source="AI",
        status="VALIDATED",
    )
    db.add(rec_validated)
    db.commit()

    return {
        "incident_id": incident.id,
        "proposed_id": rec_proposed.id,
        "validated_id": rec_validated.id,
    }


def test_approve_valid_recommendation_200(client: TestClient, test_db: Session) -> None:
    """1, 3, 4, 15: POST approve valid recommendation returns 200, status APPROVED."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john", "comment": "Rush replenishment"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_id"] == ids["proposed_id"]
    assert payload["status"] == "APPROVED"
    assert payload["incident_status"] == "RESOLVED"
    assert payload["planner_id"] == "planner_john"
    assert payload["comment"] == "Rush replenishment"
    assert payload["recommended_qty"] == 180
    assert payload["estimated_total_cost"] == 450.0
    assert payload["decided_at"] is not None


def test_reject_valid_recommendation_200(client: TestClient, test_db: Session) -> None:
    """2, 5, 6: POST reject valid recommendation returns 200, status REJECTED, incident OPEN."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/reject",
        json={
            "planner_id": "planner_mary",
            "rejection_reason": "Alternative local inventory available",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation_id"] == ids["validated_id"]
    assert payload["status"] == "REJECTED"
    assert payload["incident_status"] == "OPEN"
    assert payload["planner_id"] == "planner_mary"
    assert payload["rejection_reason"] == "Alternative local inventory available"


def test_approve_missing_recommendation_404(client: TestClient, test_db: Session) -> None:
    """7. Approve missing recommendation returns 404 RESOURCE_NOT_FOUND."""
    _seed_decision_test_data(test_db)

    response = client.post(
        "/api/v1/recommendations/99999/approve",
        json={"planner_id": "planner_john"},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error_code"] == "RESOURCE_NOT_FOUND"


def test_approve_already_approved_conflict_409(client: TestClient, test_db: Session) -> None:
    """8. Approving an already APPROVED recommendation returns 409 INVALID_STATE_TRANSITION."""
    ids = _seed_decision_test_data(test_db)

    # First approval succeeds
    res1 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )
    assert res1.status_code == 200

    # Second approval fails with 409
    res2 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )
    assert res2.status_code == 409
    payload = res2.json()
    assert payload["error_code"] == "INVALID_STATE_TRANSITION"


def test_reject_already_rejected_conflict_409(client: TestClient, test_db: Session) -> None:
    """9. Rejecting an already REJECTED recommendation returns 409 INVALID_STATE_TRANSITION."""
    ids = _seed_decision_test_data(test_db)

    # First rejection succeeds
    res1 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"planner_id": "planner_mary", "rejection_reason": "Reason"},
    )
    assert res1.status_code == 200

    # Second rejection fails with 409
    res2 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"planner_id": "planner_mary", "rejection_reason": "Reason"},
    )
    assert res2.status_code == 409
    payload = res2.json()
    assert payload["error_code"] == "INVALID_STATE_TRANSITION"


def test_approve_missing_planner_id_400(client: TestClient, test_db: Session) -> None:
    """10. Missing planner_id on approve returns 400 INVALID_REQUEST_BODY."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"comment": "No planner id provided"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_REQUEST_BODY"


def test_reject_missing_planner_id_400(client: TestClient, test_db: Session) -> None:
    """11. Missing planner_id on reject returns 400 INVALID_REQUEST_BODY."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"rejection_reason": "Reason only"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_REQUEST_BODY"


def test_reject_missing_rejection_reason_400(client: TestClient, test_db: Session) -> None:
    """12. Missing rejection_reason on reject returns 400 INVALID_REQUEST_BODY."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"planner_id": "planner_mary"},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error_code"] == "INVALID_REQUEST_BODY"


def test_correlation_id_propagated(client: TestClient, test_db: Session) -> None:
    """13. Correlation ID header is propagated in response."""
    ids = _seed_decision_test_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
        headers={"X-Correlation-ID": "test-correlation-uuid-999"},
    )

    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == "test-correlation-uuid-999"


def test_no_inventory_mutation(client: TestClient, test_db: Session) -> None:
    """14. Decision API endpoints do not mutate inventory balance tables."""
    ids = _seed_decision_test_data(test_db)
    initial_balances = [
        (b.dc_id, b.product_id, b.on_hand_qty) for b in test_db.query(InventoryBalance).all()
    ]

    client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )

    post_balances = [
        (b.dc_id, b.product_id, b.on_hand_qty) for b in test_db.query(InventoryBalance).all()
    ]
    assert initial_balances == post_balances
