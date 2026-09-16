"""
Application Query Service for Stockout Risk Incidents.
Provides read-only query capabilities for listing and fetching risk incidents.
Must NOT perform risk calculations, state mutations, audit logging, or recommendation calls.
"""

from app.services.dtos import RiskIncidentDetailDTO
from app.services.exceptions import ResourceNotFoundError
from app.services.interfaces import (
    DistributionCenterRepositoryInterface,
    ProductRepositoryInterface,
    RiskIncidentRepositoryInterface,
)


class RiskQueryService:
    """Application query service for reading risk incident data."""

    def __init__(
        self,
        risk_repo: RiskIncidentRepositoryInterface,
        dc_repo: DistributionCenterRepositoryInterface,
        product_repo: ProductRepositoryInterface,
    ) -> None:
        self._risk_repo = risk_repo
        self._dc_repo = dc_repo
        self._product_repo = product_repo

    def list_risks(self) -> list[RiskIncidentDetailDTO]:
        """
        Retrieves all persisted stockout risk incidents ordered by detected_at DESC.
        Resolves target DC code and product SKU for API representation.
        """
        incidents = self._risk_repo.list_incidents()
        results: list[RiskIncidentDetailDTO] = []
        for inc in incidents:
            dc = self._dc_repo.get_by_id(inc.target_dc_id)
            product = self._product_repo.get_by_id(inc.product_id)
            results.append(
                RiskIncidentDetailDTO(
                    id=inc.id,
                    incident_code=inc.incident_code,
                    target_dc_id=inc.target_dc_id,
                    target_dc_code=dc.code if dc else "UNKNOWN",
                    product_id=inc.product_id,
                    sku=product.sku if product else "UNKNOWN",
                    current_dos=inc.current_dos,
                    days_to_stockout=inc.days_to_stockout,
                    projected_stockout_date=inc.projected_stockout_date,
                    shortage_qty=float(inc.shortage_qty),
                    severity=inc.severity,
                    status=inc.status,
                    detected_at=inc.detected_at,
                )
            )
        return results

    def get_risk(self, incident_id: int) -> RiskIncidentDetailDTO:
        """
        Retrieves a single stockout risk incident by ID.
        Raises ResourceNotFoundError if incident does not exist.
        """
        inc = self._risk_repo.get_by_id(incident_id)
        if inc is None:
            raise ResourceNotFoundError(f"RiskIncident ID '{incident_id}' not found")

        dc = self._dc_repo.get_by_id(inc.target_dc_id)
        product = self._product_repo.get_by_id(inc.product_id)

        return RiskIncidentDetailDTO(
            id=inc.id,
            incident_code=inc.incident_code,
            target_dc_id=inc.target_dc_id,
            target_dc_code=dc.code if dc else "UNKNOWN",
            product_id=inc.product_id,
            sku=product.sku if product else "UNKNOWN",
            current_dos=inc.current_dos,
            days_to_stockout=inc.days_to_stockout,
            projected_stockout_date=inc.projected_stockout_date,
            shortage_qty=float(inc.shortage_qty),
            severity=inc.severity,
            status=inc.status,
            detected_at=inc.detected_at,
        )
