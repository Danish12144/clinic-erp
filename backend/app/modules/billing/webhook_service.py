"""Payment gateway webhook processing — Phase 2 (Master Handoff item 4,
"webhook processing" / "payment failure" / "refund states"). Separate
from `PaymentService` (which owns the manual/staff-recorded payment path
against an `Invoice`) since a webhook confirms/fails a booking-time
`PaymentGatewayOrder`, not an invoice payment — see that model's own
docstring for why the two ledgers are kept apart.

`resolve_tenant_id_for_provider_order` (the one cross-tenant read here,
via `platform_admin_session`) is unavoidable: a webhook delivery carries
no clinic slug and no JWT, only a `provider_order_id` — there is nothing
to scope a normal `tenant_session` to until that id is resolved. See
`PaymentGatewayOrderRepository`'s own docstring for the same reasoning
`TenantResolutionRepository.get_active_clinic_by_slug` already
established for login.
"""

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.appointments.models import AppointmentPaymentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.audit.service import record as record_audit
from app.modules.billing.models import PaymentGatewayOrderStatus
from app.modules.billing.payment_gateway import verify_razorpay_webhook_signature
from app.modules.billing.repository import PaymentGatewayOrderRepository

settings = get_settings()


class PaymentGatewayWebhookService:
    async def process_razorpay_webhook(self, *, raw_body: bytes, signature: str | None, payload: dict) -> None:
        if not settings.razorpay_webhook_secret:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Razorpay webhook is not configured")
        if not signature or not verify_razorpay_webhook_signature(
            raw_body=raw_body, signature=signature, webhook_secret=settings.razorpay_webhook_secret
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

        event = payload.get("event", "")
        if event == "payment.captured":
            await self._handle_payment_captured(payload)
        elif event == "payment.failed":
            await self._handle_payment_failed(payload)
        elif event == "refund.processed":
            await self._handle_refund_processed(payload)
        # Any other event type (order.paid, refund.created, ...) is
        # acknowledged (200) but ignored — Razorpay retries a webhook that
        # doesn't return 2xx, and there's nothing this booking-prepayment
        # flow needs from those specific events today.

    async def _payment_entity(self, payload: dict) -> dict:
        return payload.get("payload", {}).get("payment", {}).get("entity", {})

    async def _handle_payment_captured(self, payload: dict) -> None:
        entity = await self._payment_entity(payload)
        provider_order_id = entity.get("order_id")
        provider_payment_id = entity.get("id")
        if not provider_order_id or not provider_payment_id:
            return

        tenant_id = await PaymentGatewayOrderRepository.resolve_tenant_id_for_provider_order(
            provider="razorpay", provider_order_id=provider_order_id
        )
        if tenant_id is None:
            return  # Unknown order — nothing in this tenant to reconcile against.

        async with tenant_session(tenant_id) as session:
            order_repo = PaymentGatewayOrderRepository(session)
            order = await order_repo.get_by_provider_order_id(provider="razorpay", provider_order_id=provider_order_id)
            if order is None or order.status != PaymentGatewayOrderStatus.CREATED:
                return  # Already processed (webhook redelivery) or not found — idempotent no-op.

            await order_repo.mark_status(order.id, status=PaymentGatewayOrderStatus.PAID, provider_payment_id=provider_payment_id)
            appointment_repo = AppointmentRepository(session)
            await appointment_repo.set_payment_status(order.appointment_id, payment_status=AppointmentPaymentStatus.CONFIRMED)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=None, actor_role="SYSTEM",
                action="appointment.payment_confirmed", entity_type="appointment", entity_id=order.appointment_id,
                before={"payment_status": "PENDING"}, after={"payment_status": "CONFIRMED", "provider_payment_id": provider_payment_id},
            )

    async def _handle_payment_failed(self, payload: dict) -> None:
        entity = await self._payment_entity(payload)
        provider_order_id = entity.get("order_id")
        if not provider_order_id:
            return
        failure_reason = entity.get("error_description") or "Payment failed at the gateway"

        tenant_id = await PaymentGatewayOrderRepository.resolve_tenant_id_for_provider_order(
            provider="razorpay", provider_order_id=provider_order_id
        )
        if tenant_id is None:
            return

        async with tenant_session(tenant_id) as session:
            order_repo = PaymentGatewayOrderRepository(session)
            order = await order_repo.get_by_provider_order_id(provider="razorpay", provider_order_id=provider_order_id)
            if order is None or order.status != PaymentGatewayOrderStatus.CREATED:
                return

            await order_repo.mark_status(order.id, status=PaymentGatewayOrderStatus.FAILED, failure_reason=failure_reason)
            appointment_repo = AppointmentRepository(session)
            await appointment_repo.set_payment_status(order.appointment_id, payment_status=AppointmentPaymentStatus.FAILED)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=None, actor_role="SYSTEM",
                action="appointment.payment_failed", entity_type="appointment", entity_id=order.appointment_id,
                before={"payment_status": "PENDING"}, after={"payment_status": "FAILED", "reason": failure_reason},
            )

    async def _handle_refund_processed(self, payload: dict) -> None:
        entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        provider_payment_id = entity.get("payment_id")
        if not provider_payment_id:
            return
        # A refund we ourselves initiated (AppointmentService._cancel)
        # already marks the order REFUNDED synchronously — this handler
        # only matters for a refund initiated *outside* this app (e.g.
        # directly in the Razorpay dashboard), kept idempotent the same
        # way as the two handlers above.
        tenant_id = await PaymentGatewayOrderRepository.resolve_tenant_id_for_provider_payment(provider_payment_id)
        if tenant_id is None:
            return
        async with tenant_session(tenant_id) as session:
            order_repo = PaymentGatewayOrderRepository(session)
            order = await order_repo.get_by_provider_payment_id(provider_payment_id)
            if order is None or order.status == PaymentGatewayOrderStatus.REFUNDED:
                return
            await order_repo.mark_status(order.id, status=PaymentGatewayOrderStatus.REFUNDED)
            await AppointmentRepository(session).set_payment_status(order.appointment_id, payment_status=AppointmentPaymentStatus.REFUNDED)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=None, actor_role="SYSTEM",
                action="appointment.payment_refunded", entity_type="appointment", entity_id=order.appointment_id,
                before=None, after={"payment_status": "REFUNDED"},
            )
