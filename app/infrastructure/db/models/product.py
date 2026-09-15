from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base

if TYPE_CHECKING:
    from app.infrastructure.db.models.demand import DailyDemandSignal
    from app.infrastructure.db.models.inventory import InventoryBalance, InventoryPolicy
    from app.infrastructure.db.models.purchase_order import PurchaseOrder
    from app.infrastructure.db.models.recommendation import TransferRecommendation
    from app.infrastructure.db.models.risk import RiskIncident
    from app.infrastructure.db.models.supplier import SupplierProduct


class Product(Base):
    """Product entity representing catalog SKUs."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    pack_size: Mapped[int] = mapped_column(nullable=False, default=1)
    unit_weight_lbs: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    supplier_products: Mapped[list["SupplierProduct"]] = relationship(
        back_populates="product"
    )
    inventory_policies: Mapped[list["InventoryPolicy"]] = relationship(
        back_populates="product"
    )
    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(
        back_populates="product"
    )
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="product"
    )
    daily_demand_signals: Mapped[list["DailyDemandSignal"]] = relationship(
        back_populates="product"
    )
    risk_incidents: Mapped[list["RiskIncident"]] = relationship(
        back_populates="product"
    )
    transfer_recommendations: Mapped[list["TransferRecommendation"]] = relationship(
        back_populates="product"
    )
