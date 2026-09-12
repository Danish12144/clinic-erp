"""Financial Reports & Analytics Aggregation — pure read/aggregation over
Billing's own data (`invoices`/`invoice_line_items`/`payments`), plus a
doctor-ownership join through `encounters`/`consultations`. No new tables,
no writes.

Row-scoping: an Owner (`dashboard.view`) sees tenant-wide (optionally
branch- or doctor-filtered) totals; a Doctor (`dashboard.view_own`) is
always scoped to their own `doctor_id` — any `doctor_id` query param they
pass is silently overridden, not merely validated, same pattern
`AppointmentService.search_appointments` established for Doctor's "own"
schedule.
"""

import csv
import io
import uuid
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.reports.repository import ReportsRepository
from app.modules.reports.schemas import (
    BillingSummary,
    FinancialReport,
    PaymentModeAmount,
    ReportPeriod,
    ServiceTypeRevenue,
)


def _resolve_period(period: ReportPeriod, date_from: datetime | None, date_to: datetime | None) -> tuple[datetime | None, datetime | None]:
    now = datetime.now(timezone.utc)
    if period == ReportPeriod.TODAY:
        start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
        return start, now
    if period == ReportPeriod.SEVEN_DAYS:
        return now - timedelta(days=7), now
    if period == ReportPeriod.THIRTY_DAYS:
        return now - timedelta(days=30), now
    if period == ReportPeriod.ALL_TIME:
        return None, None

    # CUSTOM
    if date_from is None or date_to is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from and date_to are both required when period=custom")
    if date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "date_from must not be after date_to")
    return date_from, date_to


def _effective_doctor_scope(actor_role: str, actor_user_id: uuid.UUID, requested_doctor_id: uuid.UUID | None) -> uuid.UUID | None:
    return actor_user_id if actor_role == "DOCTOR" else requested_doctor_id


class ReportsService:
    async def get_billing_summary(
        self, *, tenant_id: uuid.UUID, period: ReportPeriod, date_from: datetime | None, date_to: datetime | None,
        branch_id: uuid.UUID | None, doctor_id: uuid.UUID | None, actor_role: str, actor_user_id: uuid.UUID,
    ) -> BillingSummary:
        window_from, window_to = _resolve_period(period, date_from, date_to)
        doctor_scope = _effective_doctor_scope(actor_role, actor_user_id, doctor_id)

        async with tenant_session(tenant_id) as session:
            repo = ReportsRepository(session)
            bills_raised = await repo.count_bills_raised(
                tenant_id=tenant_id, branch_id=branch_id, doctor_scope_user_id=doctor_scope, date_from=window_from, date_to=window_to
            )
            by_method = await repo.payments_by_method(
                tenant_id=tenant_id, branch_id=branch_id, doctor_scope_user_id=doctor_scope, date_from=window_from, date_to=window_to
            )

        total_collected = sum((collected for _, collected, _ in by_method), Decimal("0.00"))
        total_refunds = sum((refunded for _, _, refunded in by_method), Decimal("0.00"))
        return BillingSummary(
            period=period.value, date_from=window_from, date_to=window_to,
            total_collected=total_collected, total_bills_raised=bills_raised,
            payment_modes_tracked=len(by_method), total_refunds=total_refunds,
            by_payment_mode=[PaymentModeAmount(method=m, collected=c, refunded=r) for m, c, r in by_method],
        )

    async def get_financial_report(
        self, *, tenant_id: uuid.UUID, period: ReportPeriod, date_from: datetime | None, date_to: datetime | None,
        branch_id: uuid.UUID | None, doctor_id: uuid.UUID | None, actor_role: str, actor_user_id: uuid.UUID,
    ) -> FinancialReport:
        window_from, window_to = _resolve_period(period, date_from, date_to)
        doctor_scope = _effective_doctor_scope(actor_role, actor_user_id, doctor_id)

        async with tenant_session(tenant_id) as session:
            repo = ReportsRepository(session)
            total_billed = await repo.sum_billed(
                tenant_id=tenant_id, branch_id=branch_id, doctor_scope_user_id=doctor_scope, date_from=window_from, date_to=window_to
            )
            by_service = await repo.revenue_by_service_type(
                tenant_id=tenant_id, branch_id=branch_id, doctor_scope_user_id=doctor_scope, date_from=window_from, date_to=window_to
            )
            by_method = await repo.payments_by_method(
                tenant_id=tenant_id, branch_id=branch_id, doctor_scope_user_id=doctor_scope, date_from=window_from, date_to=window_to
            )

        total_collected = sum((c for _, c, _ in by_method), Decimal("0.00"))
        total_refunded = sum((r for _, _, r in by_method), Decimal("0.00"))
        return FinancialReport(
            period=period.value, date_from=window_from, date_to=window_to,
            total_billed=total_billed, total_collected=total_collected, total_refunded=total_refunded,
            net_collected=total_collected - total_refunded,
            by_service_type=[ServiceTypeRevenue(source_type=s, total_billed=t) for s, t in by_service],
            by_payment_mode=[PaymentModeAmount(method=m, collected=c, refunded=r) for m, c, r in by_method],
        )

    async def export_financial_report_csv(
        self, *, tenant_id: uuid.UUID, period: ReportPeriod, date_from: datetime | None, date_to: datetime | None,
        branch_id: uuid.UUID | None, doctor_id: uuid.UUID | None, actor_role: str, actor_user_id: uuid.UUID,
    ) -> str:
        """Phase 1 (Master Handoff item 6, "Basic reports & billing
        export") — reuses `get_financial_report` itself (same filters,
        same row-scoping) so the CSV can never disagree with the JSON
        endpoint's own numbers; just reshapes the same three summary
        sections into three small CSV blocks in one file."""
        report = await self.get_financial_report(
            tenant_id=tenant_id, period=period, date_from=date_from, date_to=date_to,
            branch_id=branch_id, doctor_id=doctor_id, actor_role=actor_role, actor_user_id=actor_user_id,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Period", report.period])
        writer.writerow(["Date From", report.date_from.isoformat() if report.date_from else ""])
        writer.writerow(["Date To", report.date_to.isoformat() if report.date_to else ""])
        writer.writerow(["Total Billed", report.total_billed])
        writer.writerow(["Total Collected", report.total_collected])
        writer.writerow(["Total Refunded", report.total_refunded])
        writer.writerow(["Net Collected", report.net_collected])
        writer.writerow([])
        writer.writerow(["Revenue By Service Type"])
        writer.writerow(["Source Type", "Total Billed"])
        for row in report.by_service_type:
            writer.writerow([row.source_type, row.total_billed])
        writer.writerow([])
        writer.writerow(["Revenue By Payment Mode"])
        writer.writerow(["Method", "Collected", "Refunded"])
        for row in report.by_payment_mode:
            writer.writerow([row.method, row.collected, row.refunded])
        return buffer.getvalue()
