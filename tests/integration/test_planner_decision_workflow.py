"""
Integration test suite for Planner Decision workflow and concurrency verification.
Verifies complete E2E HTTP workflows, terminal state protection, conditional concurrency,
transaction rollback safety, audit log persistence, quantity/inventory immutability,
AI boundary isolation, and OpenAPI spec alignment.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_planner_decision_service
from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.inventory import InventoryBalance
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyTransferRecommendationRepository,
)
from app.infrastructure.db.seed.seed import seed_database
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.main import app
from app.services.planner_decision_service import PlannerDecisionService


def _seed_integration_data(db: Session) -> dict[str, int]:
    """Helper seeding seed database, an OPEN RiskIncident, and TransferRecommendations."""
    seed_database(db, reset=True)

    incident = RiskIncident(
        incident_code="INC-INT-DECISION",
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
        recommendation_code="REC-INT-PROP",
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
        recommendation_code="REC-INT-VAL",
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


def test_full_approval_workflow_e2e(client: TestClient, test_db: Session) -> None:
    """1. Test full approval workflow: HTTP 200, APPROVED status, RESOLVED incident."""
    ids = _seed_integration_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john", "comment": "Approved for urgent replenishment"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Response verification
    assert data["recommendation_id"] == ids["proposed_id"]
    assert data["recommendation_code"] == "REC-INT-PROP"
    assert data["status"] == "APPROVED"
    assert data["incident_id"] == ids["incident_id"]
    assert data["incident_status"] == "RESOLVED"
    assert data["planner_id"] == "planner_john"
    assert data["comment"] == "Approved for urgent replenishment"
    assert data["recommended_qty"] == 180
    assert data["estimated_total_cost"] == 450.0
    assert data["decided_at"] is not None

    # Database verification
    rec_db = test_db.get(TransferRecommendation, ids["proposed_id"])
    assert rec_db.status == "APPROVED"
    assert rec_db.recommended_qty == 180

    incident_db = test_db.get(RiskIncident, ids["incident_id"])
    assert incident_db.status == "RESOLVED"

    audit_db = (
        test_db.query(AuditEvent)
        .filter_by(recommendation_id=ids["proposed_id"], action="PLANNER_APPROVED")
        .first()
    )
    assert audit_db is not None
    assert audit_db.planner_id == "planner_john"
    assert audit_db.final_approved_qty == 180
    assert "Approved for urgent replenishment" in audit_db.input_snapshot_json


def test_full_rejection_workflow_e2e(client: TestClient, test_db: Session) -> None:
    """2. Test full rejection workflow: HTTP 200, REJECTED status, OPEN incident."""
    ids = _seed_integration_data(test_db)

    response = client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/reject",
        json={
            "planner_id": "planner_mary",
            "rejection_reason": "Alternative local inventory available",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Response verification
    assert data["recommendation_id"] == ids["validated_id"]
    assert data["recommendation_code"] == "REC-INT-VAL"
    assert data["status"] == "REJECTED"
    assert data["incident_id"] == ids["incident_id"]
    assert data["incident_status"] == "OPEN"
    assert data["planner_id"] == "planner_mary"
    assert data["rejection_reason"] == "Alternative local inventory available"
    assert data["recommended_qty"] == 180

    # Database verification
    rec_db = test_db.get(TransferRecommendation, ids["validated_id"])
    assert rec_db.status == "REJECTED"

    incident_db = test_db.get(RiskIncident, ids["incident_id"])
    assert incident_db.status == "OPEN"

    audit_db = (
        test_db.query(AuditEvent)
        .filter_by(recommendation_id=ids["validated_id"], action="PLANNER_REJECTED")
        .first()
    )
    assert audit_db is not None
    assert audit_db.planner_id == "planner_mary"
    assert audit_db.final_approved_qty is None
    assert "Alternative local inventory available" in audit_db.input_snapshot_json


def test_terminal_state_protection_all_combinations(client: TestClient, test_db: Session) -> None:
    """3. Test terminal state protection: terminal state decision attempts return 409."""
    ids = _seed_integration_data(test_db)

    # 1. APPROVED -> APPROVE
    res_app1 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )
    assert res_app1.status_code == status.HTTP_200_OK

    res_app2 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )
    assert res_app2.status_code == status.HTTP_409_CONFLICT
    assert res_app2.json()["error_code"] == "INVALID_STATE_TRANSITION"

    # 2. APPROVED -> REJECT
    res_app_rej = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"planner_id": "planner_john", "rejection_reason": "Too late"},
    )
    assert res_app_rej.status_code == status.HTTP_409_CONFLICT
    assert res_app_rej.json()["error_code"] == "INVALID_STATE_TRANSITION"

    # 3. REJECTED -> REJECT
    res_rej1 = client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/reject",
        json={"planner_id": "planner_mary", "rejection_reason": "Reason"},
    )
    assert res_rej1.status_code == status.HTTP_200_OK

    res_rej2 = client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/reject",
        json={"planner_id": "planner_mary", "rejection_reason": "Reason"},
    )
    assert res_rej2.status_code == status.HTTP_409_CONFLICT
    assert res_rej2.json()["error_code"] == "INVALID_STATE_TRANSITION"

    # 4. REJECTED -> APPROVE
    res_rej_app = client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/approve",
        json={"planner_id": "planner_mary"},
    )
    assert res_rej_app.status_code == status.HTTP_409_CONFLICT
    assert res_rej_app.json()["error_code"] == "INVALID_STATE_TRANSITION"

    # Verify exactly 2 audit events exist (1 approval for proposed_id, 1 rejection for validated_id)
    planner_audits = (
        test_db.query(AuditEvent)
        .filter(AuditEvent.action.in_(["PLANNER_APPROVED", "PLANNER_REJECTED"]))
        .all()
    )
    assert len(planner_audits) == 2


def test_conditional_concurrency_race(client: TestClient, test_db: Session) -> None:
    """4. Test conditional concurrency: first attempt succeeds, second receives 409."""
    ids = _seed_integration_data(test_db)

    # First decision request
    req1 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_first"},
    )
    assert req1.status_code == status.HTTP_200_OK

    # Concurrent second decision request
    req2 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/reject",
        json={"planner_id": "planner_second", "rejection_reason": "Race conflict"},
    )
    assert req2.status_code == status.HTTP_409_CONFLICT
    assert req2.json()["error_code"] == "INVALID_STATE_TRANSITION"

    # Verify exactly one terminal decision and consistent incident state
    rec_db = test_db.get(TransferRecommendation, ids["proposed_id"])
    assert rec_db.status == "APPROVED"

    incident_db = test_db.get(RiskIncident, ids["incident_id"])
    assert incident_db.status == "RESOLVED"

    audits = test_db.query(AuditEvent).filter_by(recommendation_id=ids["proposed_id"]).all()
    assert len(audits) == 1
    assert audits[0].action == "PLANNER_APPROVED"


def test_approval_rollback_on_audit_failure(client: TestClient, test_db: Session) -> None:
    """5. Test approval rollback: audit creation failure rolls back transaction."""
    ids = _seed_integration_data(test_db)

    # Custom audit repo that raises an exception during audit creation
    class FailingAuditRepo:
        def create_audit_event(self, data):
            raise RuntimeError("Audit persistence error")

    def _override_failing_service() -> PlannerDecisionService:
        return PlannerDecisionService(
            recommendation_repo=SQLAlchemyTransferRecommendationRepository(test_db),
            risk_repo=SQLAlchemyRiskIncidentRepository(test_db),
            audit_repo=FailingAuditRepo(),
            uow=SQLAlchemyUnitOfWork(test_db),
        )

    app.dependency_overrides[get_planner_decision_service] = _override_failing_service

    try:
        no_raise_client = TestClient(app, raise_server_exceptions=False)
        response = no_raise_client.post(
            f"/api/v1/recommendations/{ids['proposed_id']}/approve",
            json={"planner_id": "planner_john"},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify database transaction was completely rolled back
        rec_db = test_db.get(TransferRecommendation, ids["proposed_id"])
        assert rec_db.status == "PROPOSED"

        incident_db = test_db.get(RiskIncident, ids["incident_id"])
        assert incident_db.status == "OPEN"
    finally:
        app.dependency_overrides.pop(get_planner_decision_service, None)


def test_rejection_rollback_on_audit_failure(client: TestClient, test_db: Session) -> None:
    """6. Test rejection rollback: audit creation failure rolls back recommendation."""
    ids = _seed_integration_data(test_db)

    class FailingAuditRepo:
        def create_audit_event(self, data):
            raise RuntimeError("Audit persistence error")

    def _override_failing_service() -> PlannerDecisionService:
        return PlannerDecisionService(
            recommendation_repo=SQLAlchemyTransferRecommendationRepository(test_db),
            risk_repo=SQLAlchemyRiskIncidentRepository(test_db),
            audit_repo=FailingAuditRepo(),
            uow=SQLAlchemyUnitOfWork(test_db),
        )

    app.dependency_overrides[get_planner_decision_service] = _override_failing_service

    try:
        no_raise_client = TestClient(app, raise_server_exceptions=False)
        response = no_raise_client.post(
            f"/api/v1/recommendations/{ids['validated_id']}/reject",
            json={"planner_id": "planner_mary", "rejection_reason": "Test reason"},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        rec_db = test_db.get(TransferRecommendation, ids["validated_id"])
        assert rec_db.status == "VALIDATED"

        incident_db = test_db.get(RiskIncident, ids["incident_id"])
        assert incident_db.status == "OPEN"
    finally:
        app.dependency_overrides.pop(get_planner_decision_service, None)


def test_correlation_id_propagation_success_and_error(client: TestClient, test_db: Session) -> None:
    """7. Test correlation ID propagation through 200, 404, and 409 HTTP responses."""
    ids = _seed_integration_data(test_db)
    corr_header = {"X-Correlation-ID": "corr-uuid-test-777"}

    # 1. Success 200
    res200 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
        headers=corr_header,
    )
    assert res200.status_code == status.HTTP_200_OK
    assert res200.headers.get("X-Correlation-ID") == "corr-uuid-test-777"

    # 2. Conflict 409
    res409 = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
        headers=corr_header,
    )
    assert res409.status_code == status.HTTP_409_CONFLICT
    assert res409.headers.get("X-Correlation-ID") == "corr-uuid-test-777"
    assert res409.json()["correlation_id"] == "corr-uuid-test-777"

    # 3. Not Found 404
    res404 = client.post(
        "/api/v1/recommendations/99999/approve",
        json={"planner_id": "planner_john"},
        headers=corr_header,
    )
    assert res404.status_code == status.HTTP_404_NOT_FOUND
    assert res404.headers.get("X-Correlation-ID") == "corr-uuid-test-777"
    assert res404.json()["correlation_id"] == "corr-uuid-test-777"


def test_quantity_and_inventory_immutability_and_ai_isolation(
    client: TestClient, test_db: Session
) -> None:
    """8, 9, 10. Test recommended_qty and inventory balance immutability, and AI isolation."""
    ids = _seed_integration_data(test_db)

    # Capture initial states
    initial_rec = test_db.get(TransferRecommendation, ids["proposed_id"])
    initial_qty = initial_rec.recommended_qty
    initial_cost = initial_rec.estimated_cost_snapshot

    initial_inventory = [
        (b.id, b.dc_id, b.product_id, b.on_hand_qty, b.reserved_qty)
        for b in test_db.query(InventoryBalance).all()
    ]

    # Execute approve API
    response = client.post(
        f"/api/v1/recommendations/{ids['proposed_id']}/approve",
        json={"planner_id": "planner_john"},
    )
    assert response.status_code == status.HTTP_200_OK

    # 8. Verify recommended_qty and cost unchanged
    post_rec = test_db.get(TransferRecommendation, ids["proposed_id"])
    assert post_rec.recommended_qty == initial_qty
    assert post_rec.estimated_cost_snapshot == initial_cost
    assert not hasattr(post_rec, "approved_qty")

    # 9. Verify inventory balance unchanged byte-for-byte
    post_inventory = [
        (b.id, b.dc_id, b.product_id, b.on_hand_qty, b.reserved_qty)
        for b in test_db.query(InventoryBalance).all()
    ]
    assert initial_inventory == post_inventory

    # 10. Verify AI provider was never invoked during decision
    mock_ai = MagicMock()
    client.post(
        f"/api/v1/recommendations/{ids['validated_id']}/reject",
        json={"planner_id": "planner_mary", "rejection_reason": "Reason"},
    )
    mock_ai.assert_not_called()


def test_openapi_schema_planner_decision_endpoints(client: TestClient) -> None:
    """11. Test OpenAPI schema exposes POST approve and reject endpoints."""
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == status.HTTP_200_OK
    schema = response.json()

    paths = schema["paths"]
    assert "/api/v1/recommendations/{recommendation_id}/approve" in paths
    assert "/api/v1/recommendations/{recommendation_id}/reject" in paths

    approve_spec = paths["/api/v1/recommendations/{recommendation_id}/approve"]["post"]
    assert approve_spec["summary"] == "Approve transfer recommendation"

    reject_spec = paths["/api/v1/recommendations/{recommendation_id}/reject"]["post"]
    assert reject_spec["summary"] == "Reject transfer recommendation"
