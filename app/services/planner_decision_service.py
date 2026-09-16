"""
PlannerDecisionService implementation.
Orchestrates planner approval and rejection for transfer recommendations.
Coordinates atomic conditional state transitions, risk incident status updates,
single-transaction persistence via UnitOfWork, and append-only audit logging.
"""

import json
from datetime import UTC, datetime

from app.domain.enums import IncidentStatus, PlannerAction, RecommendationStatus
from app.services.dtos import (
    AuditEventCreateData,
    PlannerDecisionResultDTO,
)
from app.services.exceptions import InvalidStateTransitionError, ResourceNotFoundError
from app.services.interfaces import (
    AuditRepositoryInterface,
    RiskIncidentRepositoryInterface,
    TransferRecommendationRepositoryInterface,
)
from app.services.unit_of_work import UnitOfWorkProtocol


class PlannerDecisionService:
    """
    Application Service orchestrating planner approval/rejection decisions.
    Pure application orchestration following dependency inversion.
    """

    def __init__(
        self,
        recommendation_repo: TransferRecommendationRepositoryInterface,
        risk_repo: RiskIncidentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        uow: UnitOfWorkProtocol,
    ) -> None:
        self._recommendation_repo = recommendation_repo
        self._risk_repo = risk_repo
        self._audit_repo = audit_repo
        self._uow = uow

    def approve_recommendation(
        self,
        recommendation_id: int,
        planner_id: str,
        comment: str | None = None,
    ) -> PlannerDecisionResultDTO:
        """
        Executes planner approval workflow:
        1. Load TransferRecommendation by ID (raises ResourceNotFoundError if missing).
        2. Load associated RiskIncident (raises ResourceNotFoundError if missing).
        3. Opens single write UnitOfWork transaction.
        4. Atomically transitions recommendation status to APPROVED if currently PROPOSED/VALIDATED.
        5. If conditional update affects 0 rows, raises InvalidStateTransitionError (rolls back).
        6. Updates RiskIncident status to RESOLVED.
        7. Appends PLANNER_APPROVED audit event with recommended_qty snapshot and comment.
        8. Commits UnitOfWork transaction and returns PlannerDecisionResultDTO.
        """
        rec = self._recommendation_repo.get_by_id(recommendation_id)
        if rec is None:
            raise ResourceNotFoundError(f"TransferRecommendation '{recommendation_id}' not found")

        incident = self._risk_repo.get_by_id(rec.incident_id)
        if incident is None:
            raise ResourceNotFoundError(f"RiskIncident '{rec.incident_id}' not found")

        decided_at = datetime.now(UTC)

        with self._uow:
            rows_affected = self._recommendation_repo.update_decision_status(
                recommendation_id=recommendation_id,
                new_status=RecommendationStatus.APPROVED.value,
                allowed_current_statuses=(
                    RecommendationStatus.PROPOSED.value,
                    RecommendationStatus.VALIDATED.value,
                ),
            )
            if rows_affected == 0:
                raise InvalidStateTransitionError(
                    f"TransferRecommendation '{recommendation_id}' cannot be approved "
                    f"from current status '{rec.status}'"
                )

            incident_updated = self._risk_repo.update_status(
                rec.incident_id, IncidentStatus.RESOLVED.value
            )
            if not incident_updated:
                raise ResourceNotFoundError(
                    f"Failed to update status for RiskIncident '{rec.incident_id}'"
                )

            snapshot_dict = {
                "recommendation_code": rec.recommendation_code,
                "recommended_qty": rec.recommended_qty,
                "estimated_cost_snapshot": str(rec.estimated_cost_snapshot),
            }
            if comment is not None:
                snapshot_dict["comment"] = comment

            self._audit_repo.create_audit_event(
                AuditEventCreateData(
                    incident_id=rec.incident_id,
                    recommendation_id=rec.id,
                    planner_id=planner_id,
                    action=PlannerAction.PLANNER_APPROVED.value,
                    input_snapshot_json=json.dumps(snapshot_dict),
                    final_approved_qty=rec.recommended_qty,
                )
            )

            self._uow.commit()

        return PlannerDecisionResultDTO(
            recommendation_id=rec.id,
            recommendation_code=rec.recommendation_code,
            status=RecommendationStatus.APPROVED.value,
            incident_id=rec.incident_id,
            incident_status=IncidentStatus.RESOLVED.value,
            planner_id=planner_id,
            comment=comment,
            rejection_reason=None,
            recommended_qty=rec.recommended_qty,
            estimated_total_cost=rec.estimated_cost_snapshot,
            decided_at=decided_at,
        )

    def reject_recommendation(
        self,
        recommendation_id: int,
        planner_id: str,
        rejection_reason: str,
    ) -> PlannerDecisionResultDTO:
        """
        Executes planner rejection workflow:
        1. Load TransferRecommendation by ID (raises ResourceNotFoundError if missing).
        2. Load associated RiskIncident (raises ResourceNotFoundError if missing).
        3. Opens single write UnitOfWork transaction.
        4. Atomically transitions recommendation status to REJECTED if currently PROPOSED/VALIDATED.
        5. If conditional update affects 0 rows, raises InvalidStateTransitionError (rolls back).
        6. Associated RiskIncident remains OPEN.
        7. Appends PLANNER_REJECTED audit event with rejection_reason.
        8. Commits UnitOfWork transaction and returns PlannerDecisionResultDTO.
        """
        rec = self._recommendation_repo.get_by_id(recommendation_id)
        if rec is None:
            raise ResourceNotFoundError(f"TransferRecommendation '{recommendation_id}' not found")

        incident = self._risk_repo.get_by_id(rec.incident_id)
        if incident is None:
            raise ResourceNotFoundError(f"RiskIncident '{rec.incident_id}' not found")

        decided_at = datetime.now(UTC)

        with self._uow:
            rows_affected = self._recommendation_repo.update_decision_status(
                recommendation_id=recommendation_id,
                new_status=RecommendationStatus.REJECTED.value,
                allowed_current_statuses=(
                    RecommendationStatus.PROPOSED.value,
                    RecommendationStatus.VALIDATED.value,
                ),
            )
            if rows_affected == 0:
                raise InvalidStateTransitionError(
                    f"TransferRecommendation '{recommendation_id}' cannot be rejected "
                    f"from current status '{rec.status}'"
                )

            snapshot_dict = {
                "recommendation_code": rec.recommendation_code,
                "recommended_qty": rec.recommended_qty,
                "rejection_reason": rejection_reason,
            }

            self._audit_repo.create_audit_event(
                AuditEventCreateData(
                    incident_id=rec.incident_id,
                    recommendation_id=rec.id,
                    planner_id=planner_id,
                    action=PlannerAction.PLANNER_REJECTED.value,
                    input_snapshot_json=json.dumps(snapshot_dict),
                    final_approved_qty=None,
                )
            )

            self._uow.commit()

        return PlannerDecisionResultDTO(
            recommendation_id=rec.id,
            recommendation_code=rec.recommendation_code,
            status=RecommendationStatus.REJECTED.value,
            incident_id=rec.incident_id,
            incident_status=incident.status,
            planner_id=planner_id,
            comment=None,
            rejection_reason=rejection_reason,
            recommended_qty=rec.recommended_qty,
            estimated_total_cost=rec.estimated_cost_snapshot,
            decided_at=decided_at,
        )
