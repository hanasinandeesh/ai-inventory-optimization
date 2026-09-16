"""
Unit and integration tests for PlannerDecisionService.
Verifies approval, rejection, state transitions, incident status updates,
single-transaction persistence via UnitOfWork, atomic concurrency checks,
audit event creation, and failure rollback behavior.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.models.risk import RiskIncident
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyRiskIncidentRepository,
    SQLAlchemyTransferRecommendationRepository,
)
from app.infrastructure.db.seed.seed import seed_database
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.services.exceptions import InvalidStateTransitionError, ResourceNotFoundError
from app.services.planner_decision_service import PlannerDecisionService


@pytest.fixture
def service_and_data(test_db: Session) -> dict:
    """Fixture seeding DB and instantiating PlannerDecisionService."""
    seed_database(test_db, reset=True)
    rec_repo = SQLAlchemyTransferRecommendationRepository(test_db)
    risk_repo = SQLAlchemyRiskIncidentRepository(test_db)
    audit_repo = SQLAlchemyAuditRepository(test_db)
    uow = SQLAlchemyUnitOfWork(test_db)

    # Seed an OPEN RiskIncident
    incident = RiskIncident(
        incident_code="INC-TEST-001",
        target_dc_id=1,  # DC-CHI
        product_id=1,  # SKU-8842
        current_dos=1.0,
        days_to_stockout=1.0,
        projected_stockout_date=date(2026, 9, 17),
        shortage_qty=180,
        severity="CRITICAL",
        status="OPEN",
    )
    test_db.add(incident)
    test_db.flush()

    # Seed a PROPOSED recommendation
    rec_proposed = TransferRecommendation(
        recommendation_code="REC-TEST-PROP",
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
    test_db.add(rec_proposed)

    # Seed a VALIDATED recommendation
    rec_validated = TransferRecommendation(
        recommendation_code="REC-TEST-VAL",
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
    test_db.add(rec_validated)
    test_db.commit()

    service = PlannerDecisionService(
        recommendation_repo=rec_repo,
        risk_repo=risk_repo,
        audit_repo=audit_repo,
        uow=uow,
    )

    return {
        "service": service,
        "incident_id": incident.id,
        "proposed_id": rec_proposed.id,
        "validated_id": rec_validated.id,
        "rec_repo": rec_repo,
        "risk_repo": risk_repo,
        "audit_repo": audit_repo,
    }


def test_approve_validated_recommendation(test_db: Session, service_and_data: dict) -> None:
    """1. Approve VALIDATED recommendation successfully."""
    service: PlannerDecisionService = service_and_data["service"]
    val_id: int = service_and_data["validated_id"]

    result = service.approve_recommendation(
        recommendation_id=val_id,
        planner_id="planner_john",
        comment="Approved for urgent transfer",
    )

    assert result.recommendation_id == val_id
    assert result.status == "APPROVED"
    assert result.incident_status == "RESOLVED"
    assert result.planner_id == "planner_john"
    assert result.comment == "Approved for urgent transfer"
    assert result.recommended_qty == 180
    assert result.estimated_total_cost == Decimal("450.00")

    # DB verification
    rec_db = test_db.get(TransferRecommendation, val_id)

    assert rec_db.status == "APPROVED"


def test_approve_proposed_recommendation(test_db: Session, service_and_data: dict) -> None:
    """2. Approve PROPOSED recommendation successfully."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    result = service.approve_recommendation(
        recommendation_id=prop_id,
        planner_id="planner_john",
    )

    assert result.recommendation_id == prop_id
    assert result.status == "APPROVED"
    assert result.incident_status == "RESOLVED"
    assert result.planner_id == "planner_john"
    assert result.comment is None


def test_reject_validated_recommendation(test_db: Session, service_and_data: dict) -> None:
    """3. Reject VALIDATED recommendation successfully."""
    service: PlannerDecisionService = service_and_data["service"]
    val_id: int = service_and_data["validated_id"]

    result = service.reject_recommendation(
        recommendation_id=val_id,
        planner_id="planner_mary",
        rejection_reason="Alternative local inventory available",
    )

    assert result.recommendation_id == val_id
    assert result.status == "REJECTED"
    assert result.incident_status == "OPEN"
    assert result.planner_id == "planner_mary"
    assert result.rejection_reason == "Alternative local inventory available"

    # DB verification
    rec_db = test_db.get(TransferRecommendation, val_id)

    assert rec_db.status == "REJECTED"


def test_reject_proposed_recommendation(test_db: Session, service_and_data: dict) -> None:
    """4. Reject PROPOSED recommendation successfully."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    result = service.reject_recommendation(
        recommendation_id=prop_id,
        planner_id="planner_mary",
        rejection_reason="Cost too high",
    )

    assert result.recommendation_id == prop_id
    assert result.status == "REJECTED"


def test_recommendation_not_found(service_and_data: dict) -> None:
    """5. Raise ResourceNotFoundError when recommendation ID does not exist."""
    service: PlannerDecisionService = service_and_data["service"]

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.approve_recommendation(recommendation_id=99999, planner_id="planner_john")
    assert "99999" in str(exc_info.value)


def test_incident_not_found(test_db: Session) -> None:
    """6. Raise ResourceNotFoundError when associated RiskIncident is missing."""
    rec_orphan = TransferRecommendation(
        recommendation_code="REC-ORPHAN",
        incident_id=99999,  # Non-existent incident
        source_dc_id=2,
        target_dc_id=1,
        product_id=1,
        recommended_qty=100,
        feasible_qty_snapshot=100,
        source_surplus_snapshot=200,
        transit_days_snapshot=1,
        route_unit_cost_snapshot=Decimal("1.00"),
        estimated_cost_snapshot=Decimal("100.00"),
        rationale="Orphan recommendation",
        recommendation_source="AI",
        status="PROPOSED",
    )
    test_db.add(rec_orphan)
    test_db.commit()

    service = PlannerDecisionService(
        recommendation_repo=SQLAlchemyTransferRecommendationRepository(test_db),
        risk_repo=SQLAlchemyRiskIncidentRepository(test_db),
        audit_repo=SQLAlchemyAuditRepository(test_db),
        uow=SQLAlchemyUnitOfWork(test_db),
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.approve_recommendation(recommendation_id=rec_orphan.id, planner_id="planner_john")
    assert "99999" in str(exc_info.value)


def test_already_approved_conflict(service_and_data: dict) -> None:
    """7. Re-approving an already APPROVED recommendation raises InvalidStateTransitionError."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    # First approval succeeds
    service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    # Second approval fails with conflict
    with pytest.raises(InvalidStateTransitionError):
        service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")


def test_already_rejected_conflict(service_and_data: dict) -> None:
    """8. Re-rejecting or approving an already REJECTED recommendation raises
    InvalidStateTransitionError."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    # First rejection succeeds
    service.reject_recommendation(
        recommendation_id=prop_id, planner_id="planner_mary", rejection_reason="Reason"
    )

    # Subsequent approval fails with conflict
    with pytest.raises(InvalidStateTransitionError):
        service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")


def test_conditional_update_returns_zero_no_audit(test_db: Session, service_and_data: dict) -> None:
    """9. When conditional update affects 0 rows, raises InvalidStateTransitionError
    and creates no audit."""
    service: PlannerDecisionService = service_and_data["service"]

    prop_id: int = service_and_data["proposed_id"]

    # Manually change status to APPROVED directly in DB to simulate race condition
    rec_db = test_db.get(TransferRecommendation, prop_id)

    rec_db.status = "APPROVED"
    test_db.commit()

    initial_audit_count = test_db.query(AuditEvent).count()

    with pytest.raises(InvalidStateTransitionError):
        service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    # Verify no audit event was created
    assert test_db.query(AuditEvent).count() == initial_audit_count


def test_approval_resolves_incident(test_db: Session, service_and_data: dict) -> None:
    """10. Approval updates associated RiskIncident status to RESOLVED."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]
    incident_id: int = service_and_data["incident_id"]

    service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    incident = test_db.get(RiskIncident, incident_id)

    assert incident.status == "RESOLVED"


def test_rejection_leaves_incident_open(test_db: Session, service_and_data: dict) -> None:
    """11. Rejection leaves associated RiskIncident status as OPEN."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]
    incident_id: int = service_and_data["incident_id"]

    service.reject_recommendation(
        recommendation_id=prop_id, planner_id="planner_mary", rejection_reason="Reason"
    )

    incident = test_db.get(RiskIncident, incident_id)

    assert incident.status == "OPEN"


def test_approval_creates_audit_event(test_db: Session, service_and_data: dict) -> None:
    """12. Approval creates PLANNER_APPROVED audit event."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    service.approve_recommendation(
        recommendation_id=prop_id, planner_id="planner_john", comment="Rush approval"
    )

    audit = (
        test_db.query(AuditEvent)
        .filter_by(recommendation_id=prop_id, action="PLANNER_APPROVED")
        .first()
    )
    assert audit is not None
    assert audit.planner_id == "planner_john"
    assert audit.final_approved_qty == 180
    assert "Rush approval" in audit.input_snapshot_json


def test_rejection_creates_audit_event(test_db: Session, service_and_data: dict) -> None:
    """13. Rejection creates PLANNER_REJECTED audit event."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    service.reject_recommendation(
        recommendation_id=prop_id, planner_id="planner_mary", rejection_reason="Not required"
    )

    audit = (
        test_db.query(AuditEvent)
        .filter_by(recommendation_id=prop_id, action="PLANNER_REJECTED")
        .first()
    )
    assert audit is not None
    assert audit.planner_id == "planner_mary"
    assert audit.final_approved_qty is None
    assert "Not required" in audit.input_snapshot_json


def test_approved_qty_not_modified(test_db: Session, service_and_data: dict) -> None:
    """14. recommended_qty is preserved and not altered by planner decision."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    result = service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")
    assert result.recommended_qty == 180

    rec_db = test_db.get(TransferRecommendation, prop_id)

    assert rec_db.recommended_qty == 180


def test_llm_never_called(service_and_data: dict) -> None:
    """15. PlannerDecisionService initialization does not require or call an LLM provider."""
    service: PlannerDecisionService = service_and_data["service"]
    assert not hasattr(service, "_ai_provider")


def test_inventory_never_mutated(test_db: Session, service_and_data: dict) -> None:
    """16. Planner decision operations do not mutate inventory balance tables."""
    from app.infrastructure.db.models.inventory import InventoryBalance

    initial_inventory = test_db.query(InventoryBalance).all()
    initial_balances = [(b.dc_id, b.product_id, b.on_hand_qty) for b in initial_inventory]

    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    post_inventory = test_db.query(InventoryBalance).all()
    post_balances = [(b.dc_id, b.product_id, b.on_hand_qty) for b in post_inventory]
    assert initial_balances == post_balances


def test_transaction_rollback_on_audit_failure(test_db: Session, service_and_data: dict) -> None:
    """17. If audit event creation fails, UnitOfWork rolls back all changes."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]
    incident_id: int = service_and_data["incident_id"]

    # Mock audit_repo.create_audit_event to raise an Exception
    class FailingAuditRepo:
        def create_audit_event(self, data):
            raise RuntimeError("Audit DB error")

    service._audit_repo = FailingAuditRepo()

    with pytest.raises(RuntimeError):
        service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    # Verify rollback: recommendation remains PROPOSED and incident remains OPEN
    rec_db = test_db.get(TransferRecommendation, prop_id)

    assert rec_db.status == "PROPOSED"

    incident_db = test_db.get(RiskIncident, incident_id)

    assert incident_db.status == "OPEN"


def test_transaction_rollback_on_incident_update_failure(
    test_db: Session, service_and_data: dict
) -> None:
    """18. If incident status update fails, UnitOfWork rolls back all changes."""
    service: PlannerDecisionService = service_and_data["service"]
    prop_id: int = service_and_data["proposed_id"]

    # Mock risk_repo.update_status to return False (simulate update failure)
    class FailingRiskRepo:
        def get_by_id(self, incident_id):
            return service_and_data["risk_repo"].get_by_id(incident_id)

        def update_status(self, incident_id, status):
            return False

    service._risk_repo = FailingRiskRepo()

    with pytest.raises(ResourceNotFoundError):
        service.approve_recommendation(recommendation_id=prop_id, planner_id="planner_john")

    # Verify rollback: recommendation remains PROPOSED
    rec_db = test_db.get(TransferRecommendation, prop_id)

    assert rec_db.status == "PROPOSED"
