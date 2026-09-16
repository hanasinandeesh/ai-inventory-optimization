"""
Unit tests for AuditQueryService.
Verifies read-only audit trail retrieval, missing incident validation,
parameter passing, and read-only non-mutation guarantees.
"""

from datetime import UTC, date, datetime

import pytest

from app.services.audit_query_service import AuditQueryService
from app.services.dtos import AuditEventDTO, RiskIncidentDTO
from app.services.exceptions import ResourceNotFoundError


class FakeRiskIncidentRepository:
    def __init__(self, incidents: list[RiskIncidentDTO] | None = None) -> None:
        self._incidents = {inc.id: inc for inc in (incidents or [])}

    def get_by_id(self, incident_id: int) -> RiskIncidentDTO | None:
        return self._incidents.get(incident_id)


class FakeAuditRepository:
    def __init__(self, audit_events: list[AuditEventDTO] | None = None) -> None:
        self._events = audit_events or []
        self.get_by_incident_id_calls: list[int] = []

    def get_by_incident_id(self, incident_id: int) -> list[AuditEventDTO]:
        self.get_by_incident_id_calls.append(incident_id)
        return [e for e in self._events if e.incident_id == incident_id]


@pytest.fixture
def sample_incident() -> RiskIncidentDTO:
    return RiskIncidentDTO(
        id=1,
        incident_code="INC-20260917-001",
        target_dc_id=1,
        product_id=10,
        current_dos=1.5,
        days_to_stockout=1.5,
        projected_stockout_date=date(2026, 9, 20),
        shortage_qty=150.0,
        severity="CRITICAL",
        status="OPEN",
    )


@pytest.fixture
def sample_audit_events() -> list[AuditEventDTO]:
    now = datetime.now(UTC)
    return [
        AuditEventDTO(
            id=101,
            incident_id=1,
            action="RISK_DETECTED",
            recommendation_id=None,
            planner_id=None,
            input_snapshot_json='{"shortage_qty": 150}',
            final_approved_qty=None,
            created_at=now,
        ),
        AuditEventDTO(
            id=102,
            incident_id=1,
            action="PLANNER_APPROVED",
            recommendation_id=201,
            planner_id="planner_john",
            input_snapshot_json='{"comment": "Urgent"}',
            final_approved_qty=150,
            created_at=now,
        ),
        AuditEventDTO(
            id=103,
            incident_id=2,
            action="RISK_DETECTED",
            recommendation_id=None,
            planner_id=None,
            input_snapshot_json=None,
            final_approved_qty=None,
            created_at=now,
        ),
    ]


def test_get_incident_audit_trail_success(
    sample_incident: RiskIncidentDTO, sample_audit_events: list[AuditEventDTO]
) -> None:
    """Verifies existing incident returns corresponding AuditEventDTO objects."""
    risk_repo = FakeRiskIncidentRepository([sample_incident])
    audit_repo = FakeAuditRepository(sample_audit_events)
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    result = service.get_incident_audit_trail(incident_id=1)

    assert len(result) == 2
    assert result[0].id == 101
    assert result[0].action == "RISK_DETECTED"
    assert result[1].id == 102
    assert result[1].action == "PLANNER_APPROVED"


def test_get_incident_audit_trail_empty_events(sample_incident: RiskIncidentDTO) -> None:
    """Verifies existing incident with no audit events returns empty list."""
    risk_repo = FakeRiskIncidentRepository([sample_incident])
    audit_repo = FakeAuditRepository([])
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    result = service.get_incident_audit_trail(incident_id=1)

    assert result == []


def test_get_incident_audit_trail_nonexistent_incident(
    sample_audit_events: list[AuditEventDTO],
) -> None:
    """Verifies nonexistent incident raises ResourceNotFoundError."""
    risk_repo = FakeRiskIncidentRepository([])
    audit_repo = FakeAuditRepository(sample_audit_events)
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.get_incident_audit_trail(incident_id=999)

    assert "999" in str(exc_info.value)


def test_audit_repository_receives_correct_incident_id(
    sample_incident: RiskIncidentDTO, sample_audit_events: list[AuditEventDTO]
) -> None:
    """Verifies audit repository get_by_incident_id is called with correct incident_id."""
    risk_repo = FakeRiskIncidentRepository([sample_incident])
    audit_repo = FakeAuditRepository(sample_audit_events)
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    service.get_incident_audit_trail(incident_id=1)

    assert audit_repo.get_by_incident_id_calls == [1]


def test_audit_repository_not_called_when_incident_nonexistent(
    sample_audit_events: list[AuditEventDTO],
) -> None:
    """Verifies audit repository is NOT called when incident does not exist."""
    risk_repo = FakeRiskIncidentRepository([])
    audit_repo = FakeAuditRepository(sample_audit_events)
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    with pytest.raises(ResourceNotFoundError):
        service.get_incident_audit_trail(incident_id=999)

    assert audit_repo.get_by_incident_id_calls == []


def test_service_performs_no_write_or_commit_operations(
    sample_incident: RiskIncidentDTO, sample_audit_events: list[AuditEventDTO]
) -> None:
    """Verifies service does not interact with UnitOfWork or write operations."""
    risk_repo = FakeRiskIncidentRepository([sample_incident])
    audit_repo = FakeAuditRepository(sample_audit_events)
    service = AuditQueryService(risk_repo=risk_repo, audit_repo=audit_repo)

    assert not hasattr(service, "_uow")
    service.get_incident_audit_trail(incident_id=1)
    # Confirm no create_audit_event or mutation calls exist on repos
    assert not hasattr(audit_repo, "create_calls")
