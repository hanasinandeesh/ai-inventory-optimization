"""
Tests for ProcessRiskDetectionService.
Verifies use-case orchestration, golden scenario, idempotency, transaction boundaries,
and error handling according to Phase 5.6 requirements.
Assures ZERO dependency on SQLAlchemy or ORM models in Application Services.
"""

from datetime import date, timedelta
from typing import Self

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import IncidentStatus, RiskSeverity
from app.domain.exceptions import InvalidDemandError, ZeroDemandError
from app.infrastructure.db.models.demand import DailyDemandSignal
from app.infrastructure.db.models.distribution_center import DistributionCenter
from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.repositories.sqlalchemy_repositories import (
    SQLAlchemyAuditRepository,
    SQLAlchemyDemandRepository,
    SQLAlchemyDistributionCenterRepository,
    SQLAlchemyInventoryPolicyRepository,
    SQLAlchemyInventoryRepository,
    SQLAlchemyProductRepository,
    SQLAlchemyRiskIncidentRepository,
)
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.services.dtos import (
    AuditEventCreateData,
    AuditEventDTO,
    DailyDemandSignalDTO,
    DistributionCenterDTO,
    InventoryBalanceDTO,
    InventoryPolicyDTO,
    ProductDTO,
    RiskIncidentCreateData,
    RiskIncidentDTO,
    RiskIncidentUpdateData,
)
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from app.services.process_risk_detection_service import ProcessRiskDetectionService


class FakeUnitOfWork:
    """Fake UnitOfWork tracking commit and rollback calls."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()


class FakeDistributionCenterRepository:
    def __init__(self, dcs: list[DistributionCenterDTO] | None = None) -> None:
        self._dcs = dcs or []

    def get_by_id(self, dc_id: int) -> DistributionCenterDTO | None:
        return next((d for d in self._dcs if d.id == dc_id), None)

    def get_by_code(self, code: str) -> DistributionCenterDTO | None:
        return next((d for d in self._dcs if d.code == code), None)

    def get_active_source_dcs(self, exclude_dc_id: int) -> list[DistributionCenterDTO]:
        return [d for d in self._dcs if d.id != exclude_dc_id and d.is_active]


class FakeProductRepository:
    def __init__(self, products: list[ProductDTO] | None = None) -> None:
        self._products = products or []

    def get_by_id(self, product_id: int) -> ProductDTO | None:
        return next((p for p in self._products if p.id == product_id), None)

    def get_by_sku(self, sku: str) -> ProductDTO | None:
        return next((p for p in self._products if p.sku == sku), None)


class FakeInventoryRepository:
    def __init__(self, balances: list[InventoryBalanceDTO] | None = None) -> None:
        self._balances = balances or []

    def get_balance(self, dc_id: int, product_id: int) -> InventoryBalanceDTO | None:
        return next(
            (b for b in self._balances if b.dc_id == dc_id and b.product_id == product_id),
            None,
        )


class FakeDemandRepository:
    def __init__(self, signals: list[DailyDemandSignalDTO] | None = None) -> None:
        self._signals = signals or []

    def get_daily_demand_signals(
        self, dc_id: int, product_id: int, start_date: date, end_date: date
    ) -> list[DailyDemandSignalDTO]:
        return [
            s
            for s in self._signals
            if s.dc_id == dc_id
            and s.product_id == product_id
            and start_date <= s.signal_date <= end_date
        ]


class FakeInventoryPolicyRepository:
    def __init__(self, policies: list[InventoryPolicyDTO] | None = None) -> None:
        self._policies = policies or []

    def get_active_policy(self, dc_id: int, product_id: int) -> InventoryPolicyDTO | None:
        return next(
            (
                p
                for p in self._policies
                if p.dc_id == dc_id and p.product_id == product_id and p.is_active
            ),
            None,
        )


class FakeRiskIncidentRepository:
    def __init__(self) -> None:
        self.incidents: list[RiskIncidentDTO] = []
        self._next_id = 1

    def find_existing_incident(
        self, target_dc_id: int, product_id: int, status: str = "OPEN"
    ) -> RiskIncidentDTO | None:
        return next(
            (
                inc
                for inc in self.incidents
                if inc.target_dc_id == target_dc_id
                and inc.product_id == product_id
                and inc.status == status
            ),
            None,
        )

    def create_incident(self, create_data: RiskIncidentCreateData) -> RiskIncidentDTO:
        dto = RiskIncidentDTO(
            id=self._next_id,
            incident_code=create_data.incident_code,
            target_dc_id=create_data.target_dc_id,
            product_id=create_data.product_id,
            current_dos=create_data.current_dos,
            days_to_stockout=create_data.days_to_stockout,
            projected_stockout_date=create_data.projected_stockout_date,
            shortage_qty=create_data.shortage_qty,
            severity=create_data.severity,
            status=create_data.status,
        )
        self._next_id += 1
        self.incidents.append(dto)
        return dto

    def update_incident(
        self, incident_id: int, update_data: RiskIncidentUpdateData
    ) -> RiskIncidentDTO | None:
        for idx, inc in enumerate(self.incidents):
            if inc.id == incident_id:
                updated = RiskIncidentDTO(
                    id=inc.id,
                    incident_code=inc.incident_code,
                    target_dc_id=inc.target_dc_id,
                    product_id=inc.product_id,
                    current_dos=update_data.current_dos,
                    days_to_stockout=update_data.days_to_stockout,
                    projected_stockout_date=update_data.projected_stockout_date,
                    shortage_qty=update_data.shortage_qty,
                    severity=update_data.severity,
                    status=inc.status,
                )
                self.incidents[idx] = updated
                return updated
        return None

    def get_by_id(self, incident_id: int) -> RiskIncidentDTO | None:
        return next((inc for inc in self.incidents if inc.id == incident_id), None)

    def get_by_code(self, incident_code: str) -> RiskIncidentDTO | None:
        return next((inc for inc in self.incidents if inc.incident_code == incident_code), None)

    def update_status(self, incident_id: int, status: str) -> bool:
        for idx, inc in enumerate(self.incidents):
            if inc.id == incident_id:
                self.incidents[idx] = RiskIncidentDTO(
                    id=inc.id,
                    incident_code=inc.incident_code,
                    target_dc_id=inc.target_dc_id,
                    product_id=inc.product_id,
                    current_dos=inc.current_dos,
                    days_to_stockout=inc.days_to_stockout,
                    projected_stockout_date=inc.projected_stockout_date,
                    shortage_qty=inc.shortage_qty,
                    severity=inc.severity,
                    status=status,
                )
                return True
        return False


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEventDTO] = []
        self._next_id = 1

    def create_audit_event(self, audit_data: AuditEventCreateData) -> AuditEventDTO:
        dto = AuditEventDTO(
            id=self._next_id,
            incident_id=audit_data.incident_id,
            action=audit_data.action,
            recommendation_id=audit_data.recommendation_id,
            planner_id=audit_data.planner_id,
            input_snapshot_json=audit_data.input_snapshot_json,
            final_approved_qty=audit_data.final_approved_qty,
        )
        self._next_id += 1
        self.events.append(dto)
        return dto

    def get_by_incident_id(self, incident_id: int) -> list[AuditEventDTO]:
        return [e for e in self.events if e.incident_id == incident_id]

    def get_by_recommendation_id(self, recommendation_id: int) -> list[AuditEventDTO]:
        return [e for e in self.events if e.recommendation_id == recommendation_id]


# Fixture helper to create test DTO data
def make_test_setup(
    on_hand: int = 100,
    reserved: int = 0,
    daily_demand_val: int = 40,
    demand_count: int = 14,
    safety_days: float = 7.0,
    dc_active: bool = True,
):
    dc = DistributionCenterDTO(
        id=1, code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=dc_active
    )
    product = ProductDTO(
        id=10, sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )
    balance = InventoryBalanceDTO(
        id=100, dc_id=1, product_id=10, on_hand_qty=on_hand, reserved_qty=reserved
    )
    policy = InventoryPolicyDTO(
        id=200, dc_id=1, product_id=10, safety_stock_days=safety_days, is_active=True
    )

    detection_date = date(2026, 9, 16)
    start_date = detection_date - timedelta(days=13)
    signals = [
        DailyDemandSignalDTO(
            id=i + 1,
            dc_id=1,
            product_id=10,
            signal_date=start_date + timedelta(days=i),
            daily_demand_qty=daily_demand_val,
        )
        for i in range(demand_count)
    ]

    return dc, product, balance, policy, signals, detection_date


def test_golden_scenario_risk_detection():
    """1. Golden scenario: 100 available, 40/day demand -> DUS 2.5, shortage 180, CRITICAL."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    result = service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert result.days_to_stockout == 2.5
    assert result.shortage_quantity == 180
    assert result.severity == RiskSeverity.CRITICAL.value
    assert result.projected_stockout_date == date(2026, 9, 18)
    assert result.status == IncidentStatus.OPEN.value
    assert result.is_new_incident is True
    assert uow.committed is True

    assert len(risk_repo.incidents) == 1
    assert len(audit_repo.events) == 1
    assert audit_repo.events[0].action == "RISK_DETECTED"


def test_missing_target_dc():
    """2. Missing target DC raises ResourceNotFoundError."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.process_risk_detection("NONEXISTENT", "SKU-8842", detection_date)

    assert "NONEXISTENT" in str(exc_info.value)
    assert uow.rolled_back is True


def test_inactive_target_dc():
    """3. Inactive target DC raises ResourceInactiveError."""
    dc, product, balance, policy, signals, detection_date = make_test_setup(dc_active=False)

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(ResourceInactiveError) as exc_info:
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert "inactive" in str(exc_info.value)
    assert uow.rolled_back is True


def test_missing_inventory_balance():
    """4. Missing inventory balance raises ResourceNotFoundError."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert "Inventory balance not found" in str(exc_info.value)
    assert uow.rolled_back is True


def test_missing_inventory_policy():
    """5. Missing inventory policy raises ResourceNotFoundError."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(ResourceNotFoundError) as exc_info:
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert "policy not found" in str(exc_info.value)
    assert uow.rolled_back is True


def test_incomplete_demand_signals():
    """6. Incomplete demand signals (< 14) raises InvalidDemandError."""
    dc, product, balance, policy, signals, detection_date = make_test_setup(demand_count=10)

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(InvalidDemandError):
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert len(risk_repo.incidents) == 0
    assert len(audit_repo.events) == 0
    assert uow.rolled_back is True


def test_zero_average_demand():
    """7. Zero average demand raises ZeroDemandError per domain logic."""
    dc, product, balance, policy, signals, detection_date = make_test_setup(daily_demand_val=0)

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    with pytest.raises(ZeroDemandError):
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert uow.rolled_back is True


def test_repeated_detection_idempotency():
    """8. Repeated risk detection reuses existing OPEN incident without creating duplicates."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    # First run
    res1 = service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)
    assert res1.is_new_incident is True
    assert len(risk_repo.incidents) == 1

    # Second run (repeated detection)
    res2 = service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)
    assert res2.is_new_incident is False
    assert res2.incident_id == res1.incident_id
    assert len(risk_repo.incidents) == 1  # No duplicate created!
    assert len(audit_repo.events) == 2    # Second audit event recorded


def test_severity_boundary_cases():
    """9. Test severity boundaries through service orchestration."""
    dc, product, balance, policy, signals, detection_date = make_test_setup(
        on_hand=200, daily_demand_val=40  # 200 / 40 = 5.0 days
    )

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)
    policy_repo = FakeInventoryPolicyRepository([policy])
    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    result = service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert result.days_to_stockout == 5.0
    assert result.severity == RiskSeverity.HIGH.value


def test_transaction_rollback_on_failure():
    """10. Verify transaction rollback when an exception occurs inside service."""
    dc, product, balance, policy, signals, detection_date = make_test_setup()

    dc_repo = FakeDistributionCenterRepository([dc])
    prod_repo = FakeProductRepository([product])
    inv_repo = FakeInventoryRepository([balance])
    demand_repo = FakeDemandRepository(signals)

    class BrokenPolicyRepo:
        def get_active_policy(self, dc_id: int, product_id: int):
            raise RuntimeError("Database connection lost")

    risk_repo = FakeRiskIncidentRepository()
    audit_repo = FakeAuditRepository()
    uow = FakeUnitOfWork()

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, BrokenPolicyRepo(), risk_repo, audit_repo, uow
    )

    with pytest.raises(RuntimeError):
        service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert uow.rolled_back is True
    assert uow.committed is False


def test_no_prohibited_imports_in_service():
    """12. Verify service file contains no imports from prohibited frameworks or ORM models."""
    import app.services.process_risk_detection_service as service_module

    mod_dict = service_module.__dict__

    prohibited = ["sqlalchemy", "fastapi", "pydantic", "app.infrastructure"]
    for item in prohibited:
        assert item not in mod_dict, f"Service module imports prohibited package '{item}'"

    # Also verify imports inspectable source text does NOT reference app.infrastructure.db.models
    import inspect
    source = inspect.getsource(service_module)
    assert "app.infrastructure" not in source


def test_sqlalchemy_integration_golden_scenario(test_db: Session):
    """Integration test verifying ProcessRiskDetectionService with real SQLAlchemy repos & UoW."""
    dc = DistributionCenter(
        code="DC-CHI", name="Chicago DC", city="Chicago", state="IL", is_active=True
    )
    product = Product(
        sku="SKU-8842", name="Salmon Fillets", category="Seafood", unit_of_measure="CS"
    )
    test_db.add_all([dc, product])
    test_db.commit()

    balance = InventoryBalance(
        dc_id=dc.id, product_id=product.id, on_hand_qty=100, reserved_qty=0
    )
    policy = InventoryPolicy(
        dc_id=dc.id, product_id=product.id, safety_stock_days=7.0, is_active=True
    )
    test_db.add_all([balance, policy])

    detection_date = date(2026, 9, 16)
    start_date = detection_date - timedelta(days=13)
    signals = [
        DailyDemandSignal(
            dc_id=dc.id,
            product_id=product.id,
            signal_date=start_date + timedelta(days=i),
            daily_demand_qty=40,
        )
        for i in range(14)
    ]
    test_db.add_all(signals)
    test_db.commit()

    # Wire real repositories and unit of work
    dc_repo = SQLAlchemyDistributionCenterRepository(test_db)
    prod_repo = SQLAlchemyProductRepository(test_db)
    inv_repo = SQLAlchemyInventoryRepository(test_db)
    demand_repo = SQLAlchemyDemandRepository(test_db)
    policy_repo = SQLAlchemyInventoryPolicyRepository(test_db)
    risk_repo = SQLAlchemyRiskIncidentRepository(test_db)
    audit_repo = SQLAlchemyAuditRepository(test_db)
    uow = SQLAlchemyUnitOfWork(test_db)

    service = ProcessRiskDetectionService(
        dc_repo, prod_repo, inv_repo, demand_repo, policy_repo, risk_repo, audit_repo, uow
    )

    result = service.process_risk_detection("DC-CHI", "SKU-8842", detection_date)

    assert result.days_to_stockout == 2.5
    assert result.shortage_quantity == 180
    assert result.severity == RiskSeverity.CRITICAL.value
    assert result.projected_stockout_date == date(2026, 9, 18)

    # Verify database persistence after transaction commit
    saved_incident = risk_repo.get_by_id(result.incident_id)
    assert saved_incident is not None
    assert saved_incident.days_to_stockout == 2.5
    assert saved_incident.severity == "CRITICAL"

    saved_audits = audit_repo.get_by_incident_id(result.incident_id)
    assert len(saved_audits) == 1
    assert saved_audits[0].action == "RISK_DETECTED"
