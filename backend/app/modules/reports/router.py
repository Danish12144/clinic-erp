"""API surface for Financial Reports & Analytics Aggregation:
`GET /api/v1/billing/summary` (KPI cards) and
`GET /api/v1/reports/financial` (detailed breakdown).

Both routes are gated by `require_any_permission("dashboard.view",
"dashboard.view_own")` — Owner holds the former (tenant-wide, matching the
PRD §3 matrix), Doctor holds the latter (row-scoped to their own
`doctor_id`, a deliberate deviation from the matrix's Owner-only default —
see migration `0015`'s docstring). No other role has either permission.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_any_permission
from app.modules.reports.schemas import BillingSummary, FinancialReport, ReportPeriod
from app.modules.reports.service import ReportsService

billing_summary_router = APIRouter(prefix="/api/v1/billing", tags=["reports"])
financial_report_router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_DASHBOARD_PERMS = ("dashboard.view", "dashboard.view_own")


def get_reports_service() -> ReportsService:
    return ReportsService()


@billing_summary_router.get("/summary", response_model=BillingSummary)
async def get_billing_summary(
    period: ReportPeriod = Query(ReportPeriod.ALL_TIME),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    branch_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_any_permission(*_DASHBOARD_PERMS)),
    service: ReportsService = Depends(get_reports_service),
) -> BillingSummary:
    return await service.get_billing_summary(
        tenant_id=current_user.tenant_id, period=period, date_from=date_from, date_to=date_to,
        branch_id=branch_id, doctor_id=doctor_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id,
    )


@financial_report_router.get("/financial", response_model=FinancialReport)
async def get_financial_report(
    period: ReportPeriod = Query(ReportPeriod.ALL_TIME),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    branch_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_any_permission(*_DASHBOARD_PERMS)),
    service: ReportsService = Depends(get_reports_service),
) -> FinancialReport:
    return await service.get_financial_report(
        tenant_id=current_user.tenant_id, period=period, date_from=date_from, date_to=date_to,
        branch_id=branch_id, doctor_id=doctor_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id,
    )
