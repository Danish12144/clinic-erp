"""Billing, Invoices & Payments business logic — see
app/modules/billing/models.py's module docstring and
PRD-ARCHITECTURE.md §5.1 (steps 11-12), §17.

`Invoice.status` is always derived, never set directly by a caller:
DRAFT -> ISSUED happens only via `issue_invoice` (requires >=1 line item);
ISSUED/PARTIALLY_PAID -> PARTIALLY_PAID/PAID/back-to-ISSUED happens only
via `_recompute_status_from_payments`, called after every payment/refund;
-> VOID happens only via `void_invoice`. Nothing else ever writes
`Invoice.status`.

Row-scoping for reads (no "(own)" qualifier issue here — the matrix marks
Doctor "R (own)" and Patient "O (own)" explicitly): Doctor sees only
invoices for encounters whose Consultation they own; Patient sees only
their own `patient_id`. Owner/Receptionist (`billing.manage`) are
tenant-wide, unscoped.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.billing.models import Invoice, InvoiceStatus, PaymentMethod
from app.modules.billing.payment_gateway import get_payment_gateway_adapter
from app.modules.billing.repository import InvoiceRepository, PaymentRepository
from app.modules.billing.schemas import (
    AutoGenerateInvoiceRequest,
    InvoiceCreateRequest,
    InvoiceLineItemCreateRequest,
    InvoiceLineItemSummary,
    InvoiceLineItemUpdateRequest,
    InvoiceListResponse,
    InvoiceSummary,
    InvoiceUpdateRequest,
    InvoiceVoidRequest,
    PaymentCreateRequest,
    PaymentListResponse,
    PaymentOrderResponse,
    PaymentSummary,
)
from app.modules.checkin.repository import EncounterRepository
from app.modules.consultation.repository import ConsultationRepository
from app.modules.doctors.repository import DoctorRepository
from app.modules.notifications.models import CommChannel
from app.modules.notifications.service import dispatch_notification
from app.modules.patients.repository import PatientRepository
from app.modules.tenancy.repository import BranchRepository

_REVERSAL_NOTE = "Automatic reversal for invoice void"


def _to_summary(invoice: Invoice) -> InvoiceSummary:
    total_paid = sum((p.amount for p in invoice.payments), Decimal("0.00"))
    return InvoiceSummary(
        id=invoice.id, tenant_id=invoice.tenant_id, branch_id=invoice.branch_id, encounter_id=invoice.encounter_id,
        patient_id=invoice.patient_id, subtotal=invoice.subtotal, tax=invoice.tax, discount=invoice.discount,
        total=invoice.total, status=invoice.status.value, voided_at=invoice.voided_at, voided_reason=invoice.voided_reason,
        total_paid=total_paid, balance_due=Decimal(invoice.total) - total_paid,
        created_at=invoice.created_at, updated_at=invoice.updated_at,
        line_items=[InvoiceLineItemSummary.model_validate(i) for i in invoice.line_items],
        payments=[PaymentSummary.model_validate(p) for p in invoice.payments],
    )


async def _doctor_owns_invoice(session, invoice: Invoice, doctor_user_id: uuid.UUID) -> bool:
    if invoice.encounter_id is None:
        return False
    consultation = await ConsultationRepository(session).get_by_encounter_id(invoice.encounter_id)
    return consultation is not None and consultation.doctor_id == doctor_user_id


class BillingService:
    async def _recompute_totals(self, session, invoice_id: uuid.UUID) -> None:
        repo = InvoiceRepository(session)
        invoice = await repo.get_by_id(invoice_id)
        assert invoice is not None
        subtotal = await repo.sum_line_items(invoice_id)
        total = subtotal - Decimal(invoice.discount) + Decimal(invoice.tax)
        await repo.update_fields(invoice_id, subtotal=subtotal, total=total)

    async def create_invoice(self, *, tenant_id: uuid.UUID, payload: InvoiceCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            if await BranchRepository(session).get_by_id(payload.branch_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{payload.branch_id}' does not exist")
            if await PatientRepository(session).get_by_id(payload.patient_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Patient '{payload.patient_id}' does not exist")
            if payload.encounter_id is not None and await EncounterRepository(session).get_by_id(payload.encounter_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")

            repo = InvoiceRepository(session)
            invoice = await repo.create(
                tenant_id=tenant_id, branch_id=payload.branch_id, patient_id=payload.patient_id,
                encounter_id=payload.encounter_id, tax=payload.tax, discount=payload.discount,
            )
            for item in payload.line_items:
                await repo.add_line_item(
                    tenant_id=tenant_id, invoice_id=invoice.id, source_type=item.source_type, source_id=item.source_id,
                    description=item.description, quantity=item.quantity, unit_price=item.unit_price,
                )
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.create", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def auto_generate_invoice(self, *, tenant_id: uuid.UUID, payload: AutoGenerateInvoiceRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(payload.encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")

            consultation = await ConsultationRepository(session).get_by_encounter_id(encounter.id)
            if consultation is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No consultation has been started for this encounter yet")

            # Guards against a double-invoice for the same encounter — e.g.
            # a receptionist manually auto-generating one mid-visit, then
            # ConsultationService.complete_consultation trying again on
            # completion (see that method's own docstring for why it calls
            # this at all). A VOID invoice doesn't count as "already
            # billed" — voiding is meant to let a fresh one be raised.
            existing_invoices, _ = await InvoiceRepository(session).search(
                tenant_id=tenant_id, branch_id=None, patient_id=None, encounter_id=encounter.id,
                status=None, doctor_scope_user_id=None, limit=50, offset=0,
            )
            if any(inv.status != InvoiceStatus.VOID for inv in existing_invoices):
                raise HTTPException(status.HTTP_409_CONFLICT, "An invoice already exists for this encounter")

            found = await DoctorRepository(session).get_user_and_profile(consultation.doctor_id)
            fee = found[1].consultation_fee if found else None
            if not fee or fee <= 0:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The consulting doctor has no consultation fee configured")

            repo = InvoiceRepository(session)
            invoice = await repo.create(
                tenant_id=tenant_id, branch_id=encounter.branch_id, patient_id=encounter.patient_id,
                encounter_id=encounter.id, tax=Decimal("0"), discount=Decimal("0"),
            )
            await repo.add_line_item(
                tenant_id=tenant_id, invoice_id=invoice.id, source_type="CONSULTATION", source_id=consultation.id,
                description="Consultation Fee", quantity=Decimal("1"), unit_price=Decimal(str(fee)),
            )
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.auto_generate", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def add_line_item(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceLineItemCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            repo = InvoiceRepository(session)
            invoice = await repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status != InvoiceStatus.DRAFT:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot add a line item to an invoice with status {invoice.status.value}")

            await repo.add_line_item(
                tenant_id=tenant_id, invoice_id=invoice.id, source_type=payload.source_type, source_id=payload.source_id,
                description=payload.description, quantity=payload.quantity, unit_price=payload.unit_price,
            )
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.line_item_add", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_line_item(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, item_id: uuid.UUID, payload: InvoiceLineItemUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            repo = InvoiceRepository(session)
            invoice = await repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status != InvoiceStatus.DRAFT:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot edit a line item on an invoice with status {invoice.status.value}")

            item = await repo.get_line_item(item_id)
            if item is None or item.invoice_id != invoice.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Line item not found")

            changes = payload.model_dump(exclude_unset=True)
            new_quantity = changes.get("quantity", item.quantity)
            new_unit_price = changes.get("unit_price", item.unit_price)
            changes["total"] = Decimal(str(new_quantity)) * Decimal(str(new_unit_price))
            await repo.update_line_item(item_id, **changes)
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.line_item_update", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def delete_line_item(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, item_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            repo = InvoiceRepository(session)
            invoice = await repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status != InvoiceStatus.DRAFT:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot remove a line item from an invoice with status {invoice.status.value}")

            item = await repo.get_line_item(item_id)
            if item is None or item.invoice_id != invoice.id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Line item not found")

            await repo.delete_line_item(item_id)
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.line_item_remove", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_invoice(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            repo = InvoiceRepository(session)
            invoice = await repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status != InvoiceStatus.DRAFT:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot edit an invoice with status {invoice.status.value}")

            changes = payload.model_dump(exclude_unset=True)
            await repo.update_fields(invoice.id, **changes)
            await self._recompute_totals(session, invoice.id)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.update", entity_type="invoice", entity_id=invoice.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def issue_invoice(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            repo = InvoiceRepository(session)
            invoice = await repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status != InvoiceStatus.DRAFT:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot issue an invoice with status {invoice.status.value}")
            if not invoice.line_items:
                raise HTTPException(status.HTTP_409_CONFLICT, "Cannot issue an invoice with no line items")

            await repo.update_fields(invoice.id, status=InvoiceStatus.ISSUED)
            full = await repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.issue", entity_type="invoice", entity_id=invoice.id,
                before={"status": InvoiceStatus.DRAFT.value}, after={"status": InvoiceStatus.ISSUED.value},
            )
            return summary

    async def void_invoice(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, payload: InvoiceVoidRequest, actor_user_id: uuid.UUID, actor_role: str) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            invoice_repo = InvoiceRepository(session)
            invoice = await invoice_repo.get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status == InvoiceStatus.VOID:
                raise HTTPException(status.HTTP_409_CONFLICT, "Invoice is already void")

            before_status = invoice.status
            payment_repo = PaymentRepository(session)
            total_paid = await payment_repo.sum_amount(invoice.id)
            if total_paid > 0:
                # PRD §5.4: voiding an already (partially) paid invoice
                # gets "a reversing entry", never mutates/deletes the
                # original payments.
                await payment_repo.create(
                    tenant_id=tenant_id, invoice_id=invoice.id, amount=-total_paid, method=PaymentMethod.OTHER,
                    gateway_reference=None, notes=_REVERSAL_NOTE, recorded_by=actor_user_id,
                )

            await invoice_repo.update_fields(
                invoice.id, status=InvoiceStatus.VOID, voided_at=datetime.now(timezone.utc), voided_reason=payload.reason
            )
            full = await invoice_repo.get_by_id(invoice.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="invoice.void", entity_type="invoice", entity_id=invoice.id,
                before={"status": before_status.value}, after={"status": InvoiceStatus.VOID.value, "reason": payload.reason},
            )
            return summary

    async def search_invoices(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, patient_id: uuid.UUID | None, encounter_id: uuid.UUID | None,
        status_filter: InvoiceStatus | None, actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int,
    ) -> InvoiceListResponse:
        doctor_scope = actor_user_id if actor_role == "DOCTOR" else None
        async with tenant_session(tenant_id) as session:
            effective_patient_id = patient_id
            if actor_role == "PATIENT":
                own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
                if own_patient is None:
                    return InvoiceListResponse(items=[], total=0, limit=limit, offset=offset)
                effective_patient_id = own_patient.id

            rows, total = await InvoiceRepository(session).search(
                tenant_id=tenant_id, branch_id=branch_id, patient_id=effective_patient_id, encounter_id=encounter_id,
                status=status_filter, doctor_scope_user_id=doctor_scope, limit=limit, offset=offset,
            )
            return InvoiceListResponse(items=[_to_summary(i) for i in rows], total=total, limit=limit, offset=offset)

    async def get_my_invoices(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int) -> InvoiceListResponse:
        async with tenant_session(tenant_id) as session:
            patient = await PatientRepository(session).get_by_user_id(user_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No patient record is linked to this account")
            rows, total = await InvoiceRepository(session).search(
                tenant_id=tenant_id, branch_id=None, patient_id=patient.id, encounter_id=None,
                status=None, doctor_scope_user_id=None, limit=limit, offset=offset,
            )
            return InvoiceListResponse(items=[_to_summary(i) for i in rows], total=total, limit=limit, offset=offset)

    async def get_invoice(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> InvoiceSummary:
        async with tenant_session(tenant_id) as session:
            invoice = await InvoiceRepository(session).get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if actor_role == "DOCTOR" and not await _doctor_owns_invoice(session, invoice, actor_user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if actor_role == "PATIENT":
                own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
                if own_patient is None or invoice.patient_id != own_patient.id:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            return _to_summary(invoice)


class PaymentService:
    async def record_payment(self, *, tenant_id: uuid.UUID, payload: PaymentCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> PaymentSummary:
        async with tenant_session(tenant_id) as session:
            invoice_repo = InvoiceRepository(session)
            invoice = await invoice_repo.get_by_id(payload.invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status in (InvoiceStatus.DRAFT, InvoiceStatus.VOID):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot record a payment against an invoice with status {invoice.status.value}")

            payment_repo = PaymentRepository(session)
            current_total_paid = await payment_repo.sum_amount(invoice.id)
            new_total_paid = current_total_paid + payload.amount
            if new_total_paid < 0:
                raise HTTPException(status.HTTP_409_CONFLICT, "This refund would exceed the amount already paid on the invoice")

            payment = await payment_repo.create(
                tenant_id=tenant_id, invoice_id=invoice.id, amount=payload.amount, method=payload.method,
                gateway_reference=payload.gateway_reference, notes=payload.notes, recorded_by=actor_user_id,
            )

            before_status = invoice.status
            if new_total_paid <= 0:
                new_status = InvoiceStatus.ISSUED
            elif new_total_paid >= Decimal(invoice.total):
                new_status = InvoiceStatus.PAID
            else:
                new_status = InvoiceStatus.PARTIALLY_PAID
            if new_status != before_status:
                await invoice_repo.update_fields(invoice.id, status=new_status)

            summary = PaymentSummary.model_validate(payment)
            action = "payment.refund" if payload.amount < 0 else "payment.record"
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action=action, entity_type="payment", entity_id=payment.id, before=None, after=summary.model_dump(mode="json"),
            )
            if new_status != before_status:
                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="invoice.status_change", entity_type="invoice", entity_id=invoice.id,
                    before={"status": before_status.value}, after={"status": new_status.value},
                )
            if payload.amount > 0:
                # Outbox integration (migration 0024) — a receipt for money
                # received, not a refund/reversal (payload.amount < 0).
                await dispatch_notification(
                    session, tenant_id=tenant_id, template_key="BILL_RECEIPT", channel=CommChannel.WHATSAPP,
                    patient_id=invoice.patient_id, context={"amount": str(payload.amount)},
                )
            return summary

    async def search_payments(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID | None, limit: int, offset: int) -> PaymentListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await PaymentRepository(session).search(tenant_id=tenant_id, invoice_id=invoice_id, limit=limit, offset=offset)
            return PaymentListResponse(items=[PaymentSummary.model_validate(p) for p in rows], total=total, limit=limit, offset=offset)

    async def create_payment_order(self, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str) -> PaymentOrderResponse:
        """The "hand the frontend something to redirect/open a checkout
        with" half of an online-payment flow (§17) — simulated via
        `MockPaymentGatewayAdapter`, see app/modules/billing/payment_gateway.py.
        Does not create a `Payment` row; recording that money was actually
        received still only happens via `record_payment` above, exactly as
        it does for a manual cash/card/UPI payment today."""
        async with tenant_session(tenant_id) as session:
            invoice = await InvoiceRepository(session).get_by_id(invoice_id)
            if invoice is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
            if invoice.status not in (InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID):
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot create a payment order for an invoice with status {invoice.status.value}")

            total_paid = sum((p.amount for p in invoice.payments), Decimal("0.00"))
            balance_due = Decimal(invoice.total) - total_paid
            if balance_due <= 0:
                raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has no balance due")

            order = await get_payment_gateway_adapter().create_order(amount=balance_due, currency="INR", receipt=str(invoice.id))
            response = PaymentOrderResponse(
                invoice_id=invoice.id, order_id=order.order_id, amount=order.amount, currency=order.currency,
                provider=order.provider, status=order.status,
            )
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="payment_order.create", entity_type="invoice", entity_id=invoice.id, before=None, after=response.model_dump(mode="json"),
            )
            return response
