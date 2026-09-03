from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum

from pydantic import BaseModel


class ReportPeriod(str, PyEnum):
    TODAY = "today"
    SEVEN_DAYS = "7_days"
    THIRTY_DAYS = "30_days"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


class PaymentModeAmount(BaseModel):
    method: str
    collected: Decimal
    refunded: Decimal


class ServiceTypeRevenue(BaseModel):
    source_type: str
    total_billed: Decimal


class BillingSummary(BaseModel):
    """PRD item: `GET /api/v1/billing/summary` KPI cards."""

    period: str
    date_from: datetime | None
    date_to: datetime | None
    total_collected: Decimal
    total_bills_raised: int
    payment_modes_tracked: int
    total_refunds: Decimal
    by_payment_mode: list[PaymentModeAmount]


class FinancialReport(BaseModel):
    """PRD item: `GET /api/v1/reports/financial` detailed analytics."""

    period: str
    date_from: datetime | None
    date_to: datetime | None
    total_billed: Decimal
    total_collected: Decimal
    total_refunded: Decimal
    net_collected: Decimal
    by_service_type: list[ServiceTypeRevenue]
    by_payment_mode: list[PaymentModeAmount]
