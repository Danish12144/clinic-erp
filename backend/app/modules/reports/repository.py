import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.billing.models import Invoice, InvoiceLineItem, InvoiceStatus, Payment
from app.modules.checkin.models import Encounter
from app.modules.consultation.models import Consultation

# "Raised" = presented to the patient at least once (issued), including a
# later-voided one — VOID doesn't retroactively mean it was never raised.
# "Revenue-bearing" excludes VOID (and DRAFT) — a voided bill isn't real
# revenue, so it's excluded from every money total below, not just the
# raised-count.
_RAISED_STATUSES = (InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID, InvoiceStatus.VOID)
_REVENUE_STATUSES = (InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID)


class ReportsRepository:
    """Pure aggregation over Billing's own tables (`invoices`/
    `invoice_line_items`/`payments`) plus a doctor-ownership join through
    `encounters`/`consultations`, identical to the one
    `InvoiceRepository.search` already uses for row-scoping — see
    app/modules/billing/repository.py. No new tables; this module only
    reads.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _doctor_scope(self, query, doctor_scope_user_id: uuid.UUID | None):
        if doctor_scope_user_id is None:
            return query
        return (
            query.join(Encounter, Encounter.id == Invoice.encounter_id)
            .join(Consultation, Consultation.encounter_id == Encounter.id)
            .where(Consultation.doctor_id == doctor_scope_user_id)
        )

    async def count_bills_raised(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, doctor_scope_user_id: uuid.UUID | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> int:
        filters = [Invoice.tenant_id == tenant_id, Invoice.status.in_(_RAISED_STATUSES)]
        if branch_id:
            filters.append(Invoice.branch_id == branch_id)
        if date_from:
            filters.append(Invoice.created_at >= date_from)
        if date_to:
            filters.append(Invoice.created_at <= date_to)

        query = self._doctor_scope(select(func.count()).select_from(Invoice), doctor_scope_user_id)
        result = await self._session.execute(query.where(*filters))
        return result.scalar_one()

    async def sum_billed(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, doctor_scope_user_id: uuid.UUID | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> Decimal:
        filters = [Invoice.tenant_id == tenant_id, Invoice.status.in_(_REVENUE_STATUSES)]
        if branch_id:
            filters.append(Invoice.branch_id == branch_id)
        if date_from:
            filters.append(Invoice.created_at >= date_from)
        if date_to:
            filters.append(Invoice.created_at <= date_to)

        query = self._doctor_scope(select(func.coalesce(func.sum(Invoice.total), 0)).select_from(Invoice), doctor_scope_user_id)
        result = await self._session.execute(query.where(*filters))
        # COALESCE's fallback literal (0) doesn't carry `invoices.total`'s
        # numeric(12,2) scale the way a real SUM() would, so an empty
        # aggregate comes back as Decimal("0") instead of Decimal("0.00") —
        # quantize explicitly rather than let that leak into the response.
        return Decimal(result.scalar_one()).quantize(Decimal("0.01"))

    async def revenue_by_service_type(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, doctor_scope_user_id: uuid.UUID | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> list[tuple[str, Decimal]]:
        """Sums `InvoiceLineItem.total` per `source_type` — a decomposition
        of each invoice's *subtotal*, not its post-tax/discount `total`;
        those two won't reconcile exactly when an invoice carries tax or a
        discount, since neither is attributable to one service type. Use
        `sum_billed` for the true billed total."""
        filters = [Invoice.tenant_id == tenant_id, Invoice.status.in_(_REVENUE_STATUSES)]
        if branch_id:
            filters.append(Invoice.branch_id == branch_id)
        if date_from:
            filters.append(Invoice.created_at >= date_from)
        if date_to:
            filters.append(Invoice.created_at <= date_to)

        query = (
            select(InvoiceLineItem.source_type, func.coalesce(func.sum(InvoiceLineItem.total), 0))
            .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
            .group_by(InvoiceLineItem.source_type)
        )
        query = self._doctor_scope(query, doctor_scope_user_id)
        result = await self._session.execute(query.where(*filters))
        return [(row[0].value, Decimal(row[1])) for row in result.all()]

    async def payments_by_method(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, doctor_scope_user_id: uuid.UUID | None,
        date_from: datetime | None, date_to: datetime | None,
    ) -> list[tuple[str, Decimal, Decimal]]:
        """One row per `payment_method` that had any activity in scope:
        (method, collected, refunded) — `collected` sums positive-amount
        payments, `refunded` sums the absolute value of negative-amount
        ones. A method with only refunds (no positive payment) still
        appears, e.g. if a payment recorded under one method is later
        partly refunded under another."""
        filters = [Payment.tenant_id == tenant_id]
        if date_from:
            filters.append(Payment.recorded_at >= date_from)
        if date_to:
            filters.append(Payment.recorded_at <= date_to)
        if branch_id:
            filters.append(Invoice.branch_id == branch_id)

        collected_expr = func.coalesce(func.sum(case((Payment.amount > 0, Payment.amount), else_=0)), 0)
        refunded_expr = func.coalesce(func.sum(case((Payment.amount < 0, -Payment.amount), else_=0)), 0)
        query = (
            select(Payment.method, collected_expr, refunded_expr)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .group_by(Payment.method)
        )
        query = self._doctor_scope(query, doctor_scope_user_id)
        result = await self._session.execute(query.where(*filters))
        return [(row[0].value, Decimal(row[1]), Decimal(row[2])) for row in result.all()]
