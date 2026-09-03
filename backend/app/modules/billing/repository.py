import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.billing.models import Invoice, InvoiceLineItem, InvoiceStatus, Payment
from app.modules.checkin.models import Encounter
from app.modules.consultation.models import Consultation


def _with_relations(query):
    # populate_existing=True matters here: this module calls get_by_id
    # more than once against the *same* Invoice within one request (e.g.
    # add_line_item fetches it, mutates line items, then re-fetches to
    # build the response) — without it, SQLAlchemy's identity map returns
    # the already-loaded (now-stale) line_items/payments collections
    # instead of re-querying them, since a selectinload on an object
    # that's already present is skipped by default.
    return query.options(selectinload(Invoice.line_items), selectinload(Invoice.payments)).execution_options(populate_existing=True)


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, patient_id: uuid.UUID, encounter_id: uuid.UUID | None,
        tax: Decimal, discount: Decimal,
    ) -> Invoice:
        invoice = Invoice(tenant_id=tenant_id, branch_id=branch_id, patient_id=patient_id, encounter_id=encounter_id, tax=tax, discount=discount)
        self._session.add(invoice)
        await self._session.flush()
        return invoice

    async def get_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        result = await self._session.execute(_with_relations(select(Invoice).where(Invoice.id == invoice_id)))
        return result.unique().scalar_one_or_none()

    async def update_fields(self, invoice_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Invoice).where(Invoice.id == invoice_id).values(**fields))

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        encounter_id: uuid.UUID | None,
        status: InvoiceStatus | None,
        doctor_scope_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Invoice], int]:
        filters = [Invoice.tenant_id == tenant_id]
        if branch_id:
            filters.append(Invoice.branch_id == branch_id)
        if patient_id:
            filters.append(Invoice.patient_id == patient_id)
        if encounter_id:
            filters.append(Invoice.encounter_id == encounter_id)
        if status:
            filters.append(Invoice.status == status)

        base_query = select(Invoice.id)
        count_query = select(func.count()).select_from(Invoice)
        if doctor_scope_user_id is not None:
            joined = (
                select(Invoice.id)
                .join(Encounter, Encounter.id == Invoice.encounter_id)
                .join(Consultation, Consultation.encounter_id == Encounter.id)
                .where(Consultation.doctor_id == doctor_scope_user_id)
            )
            base_query = joined
            count_query = (
                select(func.count())
                .select_from(Invoice)
                .join(Encounter, Encounter.id == Invoice.encounter_id)
                .join(Consultation, Consultation.encounter_id == Encounter.id)
                .where(Consultation.doctor_id == doctor_scope_user_id)
            )

        count_result = await self._session.execute(count_query.where(*filters))
        total = count_result.scalar_one()

        id_page = await self._session.execute(base_query.where(*filters).order_by(Invoice.created_at.desc()).limit(limit).offset(offset))
        ids = [row[0] for row in id_page.all()]
        if not ids:
            return [], total

        page_result = await self._session.execute(_with_relations(select(Invoice).where(Invoice.id.in_(ids))).order_by(Invoice.created_at.desc()))
        return list(page_result.unique().scalars().all()), total

    # ---- Line items ------------------------------------------------------

    async def add_line_item(
        self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, source_type, source_id: uuid.UUID | None,
        description: str, quantity: Decimal, unit_price: Decimal,
    ) -> InvoiceLineItem:
        item = InvoiceLineItem(
            tenant_id=tenant_id, invoice_id=invoice_id, source_type=source_type, source_id=source_id,
            description=description, quantity=quantity, unit_price=unit_price, total=quantity * unit_price,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_line_item(self, item_id: uuid.UUID) -> InvoiceLineItem | None:
        result = await self._session.execute(select(InvoiceLineItem).where(InvoiceLineItem.id == item_id))
        return result.scalar_one_or_none()

    async def update_line_item(self, item_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(InvoiceLineItem).where(InvoiceLineItem.id == item_id).values(**fields))

    async def delete_line_item(self, item_id: uuid.UUID) -> None:
        item = await self.get_line_item(item_id)
        if item is not None:
            await self._session.delete(item)
            await self._session.flush()

    async def sum_line_items(self, invoice_id: uuid.UUID) -> Decimal:
        result = await self._session.execute(
            select(func.coalesce(func.sum(InvoiceLineItem.total), 0)).where(InvoiceLineItem.invoice_id == invoice_id)
        )
        return Decimal(result.scalar_one())


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, amount: Decimal, method, gateway_reference: str | None,
        notes: str | None, recorded_by: uuid.UUID,
    ) -> Payment:
        payment = Payment(
            tenant_id=tenant_id, invoice_id=invoice_id, amount=amount, method=method,
            gateway_reference=gateway_reference, notes=notes, recorded_by=recorded_by,
        )
        self._session.add(payment)
        await self._session.flush()
        return payment

    async def sum_amount(self, invoice_id: uuid.UUID) -> Decimal:
        result = await self._session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == invoice_id))
        return Decimal(result.scalar_one())

    async def search(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID | None, limit: int, offset: int) -> tuple[list[Payment], int]:
        filters = [Payment.tenant_id == tenant_id]
        if invoice_id:
            filters.append(Payment.invoice_id == invoice_id)

        count_result = await self._session.execute(select(func.count()).select_from(Payment).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Payment).where(*filters).order_by(Payment.recorded_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total
