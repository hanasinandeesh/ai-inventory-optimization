"""
Application Query Service for Audit Events.
Provides read-only query capabilities for fetching audit event trails for risk incidents.
Must NOT perform state mutations, database writes, or recommendation calls.
"""

from app.services.dtos import AuditEventDTO
from app.services.exceptions import ResourceNotFoundError
from app.services.interfaces import (
    AuditRepositoryInterface,
    RiskIncidentRepositoryInterface,
)


class AuditQueryService:
    """Application query service for reading audit event trails."""

    def __init__(
        self,
        risk_repo: RiskIncidentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._risk_repo = risk_repo
        self._audit_repo = audit_repo

    def get_incident_audit_trail(
        self,
        incident_id: int,
    ) -> list[AuditEventDTO]:
        """
        Retrieves all audit events belonging to a risk incident.
        Raises ResourceNotFoundError if the incident does not exist.
        """
        incident = self._risk_repo.get_by_id(incident_id)
        if incident is None:
            raise ResourceNotFoundError(f"RiskIncident with id {incident_id} not found")

        return self._audit_repo.get_by_incident_id(incident_id)
