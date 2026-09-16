"""
ProcessRiskDetectionService implementation.
Orchestrates stockout risk detection use cases using domain calculations and repository protocols.
Operates strictly on application DTOs and protocols with ZERO infrastructure or ORM dependencies.
"""

import json
from datetime import UTC, date, datetime, time, timedelta

from app.domain.demand import calculate_average_daily_demand
from app.domain.enums import IncidentStatus, PlannerAction
from app.domain.inventory import calculate_available_inventory
from app.domain.risk import evaluate_stockout_risk
from app.services.dtos import (
    AuditEventCreateData,
    ProcessRiskDetectionResult,
    RiskIncidentCreateData,
    RiskIncidentUpdateData,
)
from app.services.exceptions import ResourceInactiveError, ResourceNotFoundError
from app.services.interfaces import (
    AuditRepositoryInterface,
    DemandRepositoryInterface,
    DistributionCenterRepositoryInterface,
    InventoryPolicyRepositoryInterface,
    InventoryRepositoryInterface,
    ProductRepositoryInterface,
    RiskIncidentRepositoryInterface,
    UnitOfWorkProtocol,
)


class ProcessRiskDetectionService:
    """
    Application Service orchestrating inventory stockout risk detection for a SKU at a DC.
    Pure use-case orchestrator with constructor dependency injection.
    """

    def __init__(
        self,
        dc_repo: DistributionCenterRepositoryInterface,
        product_repo: ProductRepositoryInterface,
        inventory_repo: InventoryRepositoryInterface,
        demand_repo: DemandRepositoryInterface,
        policy_repo: InventoryPolicyRepositoryInterface,
        risk_repo: RiskIncidentRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        uow: UnitOfWorkProtocol,
    ) -> None:
        self._dc_repo = dc_repo
        self._product_repo = product_repo
        self._inventory_repo = inventory_repo
        self._demand_repo = demand_repo
        self._policy_repo = policy_repo
        self._risk_repo = risk_repo
        self._audit_repo = audit_repo
        self._uow = uow

    def process_risk_detection(
        self,
        target_dc_id_or_code: int | str,
        product_id_or_sku: int | str,
        detection_date: date,
    ) -> ProcessRiskDetectionResult:
        """
        Executes stockout risk detection use-case:
        1. Resolves and validates target DC.
        2. Resolves product/SKU.
        3. Retrieves inventory balance and calculates available inventory via domain function.
        4. Retrieves exactly 14 demand signals and calculates average daily demand via
           domain function.
        5. Retrieves active inventory policy and evaluates risk via domain function.
        6. Creates or reuses existing OPEN RiskIncident (idempotent).
        7. Logs append-only system audit event.
        8. Commits transaction boundary.
        """
        with self._uow:
            # 1. Resolve target DC
            if isinstance(target_dc_id_or_code, int):
                target_dc = self._dc_repo.get_by_id(target_dc_id_or_code)
            else:
                target_dc = self._dc_repo.get_by_code(target_dc_id_or_code)

            if target_dc is None:
                raise ResourceNotFoundError(
                    f"Target distribution center '{target_dc_id_or_code}' not found"
                )

            # 2. Validate target DC is active
            if not target_dc.is_active:
                raise ResourceInactiveError(
                    f"Target distribution center '{target_dc.code}' is inactive"
                )

            # 3. Resolve product/SKU
            if isinstance(product_id_or_sku, int):
                product = self._product_repo.get_by_id(product_id_or_sku)
            else:
                product = self._product_repo.get_by_sku(product_id_or_sku)

            if product is None:
                raise ResourceNotFoundError(f"Product '{product_id_or_sku}' not found")

            # 4. Retrieve current inventory balance
            balance = self._inventory_repo.get_balance(target_dc.id, product.id)
            if balance is None:
                raise ResourceNotFoundError(
                    f"Inventory balance not found for DC '{target_dc.code}' and SKU '{product.sku}'"
                )

            # 5. Calculate available inventory using domain function
            available_qty = calculate_available_inventory(
                on_hand_qty=balance.on_hand_qty,
                reserved_qty=balance.reserved_qty,
            )

            # 6. Retrieve exactly 14 demand signals
            start_date = detection_date - timedelta(days=13)
            demand_signals = self._demand_repo.get_daily_demand_signals(
                dc_id=target_dc.id,
                product_id=product.id,
                start_date=start_date,
                end_date=detection_date,
            )

            # 7. Calculate average daily demand using domain function
            demand_quantities = [signal.daily_demand_qty for signal in demand_signals]
            average_daily_demand = calculate_average_daily_demand(demand_quantities)

            # 8. Retrieve active inventory policy
            policy = self._policy_repo.get_active_policy(target_dc.id, product.id)
            if policy is None:
                raise ResourceNotFoundError(
                    f"Active inventory policy not found for DC '{target_dc.code}' "
                    f"and SKU '{product.sku}'"
                )

            # 9. Evaluate stockout risk using domain function
            risk_assessment = evaluate_stockout_risk(
                available_inventory=available_qty,
                average_daily_demand=average_daily_demand,
                safety_stock_days=int(policy.safety_stock_days),
                detection_date=detection_date,
            )

            # 10. Check Idempotency - find existing OPEN incident
            existing_incident = self._risk_repo.find_existing_incident(
                target_dc_id=target_dc.id,
                product_id=product.id,
                status=IncidentStatus.OPEN.value,
            )

            is_new = False
            if existing_incident is not None:
                update_data = RiskIncidentUpdateData(
                    incident_id=existing_incident.id,
                    current_dos=risk_assessment.days_to_stockout,
                    days_to_stockout=risk_assessment.days_to_stockout,
                    projected_stockout_date=risk_assessment.projected_stockout_date,
                    shortage_qty=float(risk_assessment.shortage_quantity),
                    severity=risk_assessment.severity.value,
                )
                updated_dto = self._risk_repo.update_incident(existing_incident.id, update_data)
                incident_dto = updated_dto or existing_incident
            else:
                is_new = True
                incident_code = (
                    f"INC-{target_dc.code}-{product.sku}-{detection_date.strftime('%Y%m%d')}"
                )
                detected_dt = datetime.combine(detection_date, time.min, tzinfo=UTC)
                create_data = RiskIncidentCreateData(
                    incident_code=incident_code,
                    target_dc_id=target_dc.id,
                    product_id=product.id,
                    current_dos=risk_assessment.days_to_stockout,
                    days_to_stockout=risk_assessment.days_to_stockout,
                    projected_stockout_date=risk_assessment.projected_stockout_date,
                    shortage_qty=float(risk_assessment.shortage_quantity),
                    severity=risk_assessment.severity.value,
                    status=IncidentStatus.OPEN.value,
                    detected_at=detected_dt,
                )
                incident_dto = self._risk_repo.create_incident(create_data)

            # 11. Create System Audit Event
            snapshot_data = {
                "target_dc_code": target_dc.code,
                "product_sku": product.sku,
                "detection_date": str(detection_date),
                "available_inventory": available_qty,
                "average_daily_demand": average_daily_demand,
                "days_to_stockout": risk_assessment.days_to_stockout,
                "projected_stockout_date": str(risk_assessment.projected_stockout_date),
                "target_safety_stock_units": risk_assessment.target_safety_stock_units,
                "shortage_quantity": risk_assessment.shortage_quantity,
                "severity": risk_assessment.severity.value,
                "is_new_incident": is_new,
            }
            audit_create_data = AuditEventCreateData(
                incident_id=incident_dto.id,
                recommendation_id=None,
                planner_id=None,
                action=PlannerAction.RISK_DETECTED.value,
                input_snapshot_json=json.dumps(snapshot_data),
                final_approved_qty=None,
            )
            self._audit_repo.create_audit_event(audit_create_data)

            # 12. Commit transaction
            self._uow.commit()

            detected_at = incident_dto.detected_at or datetime.now()

            return ProcessRiskDetectionResult(
                incident_id=incident_dto.id,
                incident_code=incident_dto.incident_code,
                target_dc_id=target_dc.id,
                target_dc_code=target_dc.code,
                product_id=product.id,
                product_sku=product.sku,
                available_inventory=available_qty,
                average_daily_demand=average_daily_demand,
                days_to_stockout=risk_assessment.days_to_stockout,
                projected_stockout_date=risk_assessment.projected_stockout_date,
                target_safety_stock_units=risk_assessment.target_safety_stock_units,
                shortage_quantity=risk_assessment.shortage_quantity,
                severity=risk_assessment.severity.value,
                status=incident_dto.status,
                is_new_incident=is_new,
                detected_at=detected_at,
            )
