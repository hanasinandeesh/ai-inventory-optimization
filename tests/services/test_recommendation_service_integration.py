"""
Integration tests for RecommendationService using seeded Golden Scenario database.
Verifies end-to-end orchestration, prevalidation filtering (Dallas excluded before AI invocation),
AI boundary isolation (zero internal DB surrogate IDs exposed), decision snapshot persistence,
and audit logging.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.deps import get_recommendation_service
from app.infrastructure.db.models.audit import AuditEvent
from app.infrastructure.db.models.recommendation import TransferRecommendation
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyProductRepository,
    SQLAlchemyRiskIncidentRepository,
)
from app.infrastructure.db.seed.seed import seed_database
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.services.dtos import AIRecommendationInputDTO, AIRecommendationOutputDTO
from app.services.process_risk_detection_service import ProcessRiskDetectionService


class GoldenScenarioFakeAIProvider:
    """Fake AI provider for Golden Scenario integration test."""

    def __init__(self) -> None:
        self.captured_input: AIRecommendationInputDTO | None = None

    def generate_recommendation(
        self, input_data: AIRecommendationInputDTO
    ) -> AIRecommendationOutputDTO:
        self.captured_input = input_data
        return AIRecommendationOutputDTO(
            selected_candidate_id="CAND-DC-IND-DC-CHI",
            rationale="Indianapolis selected due to feasible 1-day transit lead time.",
        )


def test_recommendation_golden_scenario_database_integration(test_db: Session) -> None:
    """
    Executes full Golden Scenario integration test against seeded database:
    1. Seeds database state (Chicago, Indianapolis, Dallas, SKU-8842).
    2. Runs ProcessRiskDetectionService to generate OPEN RiskIncident for Chicago.
    3. Runs RecommendationService with GoldenScenarioFakeAIProvider.
    4. Verifies Dallas (3-day transit >= 2.5 DUS) is excluded before AI invocation.
    5. Verifies AI input contains business identifiers only and zero DB surrogate IDs.
    6. Verifies Indianapolis (180 units, $450.00 estimated cost) recommendation is persisted.
    7. Verifies decision snapshots and RECOMMENDATION_GENERATED audit log.
    """
    seed_database(test_db, reset=True)
    detection_date = date(2026, 9, 16)

    # 1. Run ProcessRiskDetectionService to generate an OPEN RiskIncident for Chicago
    risk_service = ProcessRiskDetectionService(
        risk_repo=SQLAlchemyRiskIncidentRepository(test_db),
        dc_repo=SQLAlchemyDistributionCenterRepository(test_db),
        product_repo=SQLAlchemyProductRepository(test_db),
        inventory_repo=SQLAlchemyInventoryRepository(test_db),
        demand_repo=SQLAlchemyDemandRepository(test_db),
        policy_repo=SQLAlchemyInventoryPolicyRepository(test_db),
        audit_repo=SQLAlchemyAuditRepository(test_db),
        uow=SQLAlchemyUnitOfWork(test_db),
    )
    incident_result = risk_service.process_risk_detection(
        target_dc_id_or_code="DC-CHI",
        product_id_or_sku="SKU-8842",
        detection_date=detection_date,
    )

    assert incident_result.status == "OPEN"
    assert incident_result.shortage_quantity == 180

    # 2. Wire RecommendationService using composition root and fake AI provider
    fake_ai_provider = GoldenScenarioFakeAIProvider()
    rec_service = get_recommendation_service(db=test_db, ai_provider=fake_ai_provider)

    # 3. Generate recommendation
    result = rec_service.generate_recommendation(incident_result.incident_id)

    # 4. Verify prevalidation filtering: Dallas MUST NOT reach AI input candidate list
    ai_input = fake_ai_provider.captured_input
    assert ai_input is not None
    candidate_dc_codes = [c.source_dc_code for c in ai_input.prevalidated_candidates]
    assert "DC-DAL" not in candidate_dc_codes, (
        "Dallas DC must be excluded due to transit feasibility"
    )
    assert "DC-IND" in candidate_dc_codes

    # 5. Verify AI input boundary isolation (zero internal DB surrogate IDs)
    assert ai_input.incident_code == incident_result.incident_code
    assert ai_input.target_dc_code == "DC-CHI"
    assert ai_input.product_sku == "SKU-8842"
    assert ai_input.shortage_qty == 180
    assert not hasattr(ai_input, "incident_id")
    assert not hasattr(ai_input, "target_dc_id")
    assert not hasattr(ai_input, "product_id")

    # 6. Verify RecommendationResultDTO
    assert result.has_recommendation is True
    assert result.status == "PROPOSED"
    assert result.source_dc_code == "DC-IND"
    assert result.target_dc_code == "DC-CHI"
    assert result.product_sku == "SKU-8842"
    assert result.recommended_qty == 180
    assert result.estimated_total_cost == Decimal("450.0")
    assert result.recommendation_source == "AI"

    # 7. Verify Database Persistence (TransferRecommendation record)
    db_rec = (
        test_db.query(TransferRecommendation)
        .filter_by(incident_id=incident_result.incident_id)
        .first()
    )
    assert db_rec is not None
    assert db_rec.status == "PROPOSED"
    assert db_rec.recommended_qty == 180
    assert db_rec.feasible_qty_snapshot == 180
    assert db_rec.source_surplus_snapshot == 450
    assert db_rec.transit_days_snapshot == 1
    assert db_rec.route_unit_cost_snapshot == Decimal("2.50")
    assert db_rec.estimated_cost_snapshot == Decimal("450.00")

    # 8. Verify Audit Log
    db_audit = (
        test_db.query(AuditEvent)
        .filter_by(incident_id=incident_result.incident_id, action="RECOMMENDATION_GENERATED")
        .first()
    )
    assert db_audit is not None
    assert db_audit.recommendation_id == db_rec.id
