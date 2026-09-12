"""Public (unauthenticated) clinic discovery + self-booking — Phase 2
(Master Handoff item 1). Every method resolves `clinic_slug` -> `tenant_id`
first (same `TenantResolutionRepository` the Auth module's public login
endpoints already use), then works inside a normal `tenant_session` — no
`Depends(require_permission(...))` anywhere in the router this service
backs, since there is no authenticated caller at all.

Booking reuses `app.modules.appointments.slot_validation.
validate_and_lock_slot` directly (a free function, not
`AppointmentService`) so the whole find-or-create-patient +
validate-and-lock-slot + create-appointment + create-gateway-order
sequence commits atomically in this module's own single `tenant_session`
— see that module's own docstring for why this doesn't go through
`AppointmentService` as a black box.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.appointments.models import AppointmentPaymentStatus, AppointmentSource
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.slot_validation import list_available_slots, validate_and_lock_slot
from app.modules.audit.service import record as record_audit
from app.modules.auth.repository import TenantResolutionRepository
from app.modules.billing.payment_gateway import get_payment_gateway_adapter
from app.modules.billing.repository import PaymentGatewayOrderRepository
from app.modules.doctors.repository import BranchAssignmentRepository, DoctorRepository
from app.modules.notifications.models import CommChannel
from app.modules.notifications.service import dispatch_notification
from app.modules.patients.repository import PatientRepository
from app.modules.public.schemas import (
    PublicBookingRequest,
    PublicBookingResponse,
    PublicBranchSummary,
    PublicClinicSummary,
    PublicDoctorSummary,
    PublicGatewayOrderInfo,
    PublicSlot,
    PublicSlotsResponse,
)
from app.modules.tenancy.repository import BranchRepository

settings = get_settings()


async def _resolve_clinic(clinic_slug: str):
    clinic = await TenantResolutionRepository.get_active_clinic_by_slug(clinic_slug)
    if clinic is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
    return clinic


class PublicBookingService:
    async def get_clinic(self, *, clinic_slug: str) -> PublicClinicSummary:
        clinic = await _resolve_clinic(clinic_slug)
        return PublicClinicSummary(slug=clinic.slug, name=clinic.name, timezone=clinic.timezone)

    async def list_branches(self, *, clinic_slug: str) -> list[PublicBranchSummary]:
        clinic = await _resolve_clinic(clinic_slug)
        async with tenant_session(clinic.id) as session:
            branches = await BranchRepository(session).list_all(include_inactive=False)
            return [PublicBranchSummary(id=b.id, name=b.name, address=b.address, phone=b.phone) for b in branches]

    async def list_doctors(self, *, clinic_slug: str, branch_id: uuid.UUID | None) -> list[PublicDoctorSummary]:
        clinic = await _resolve_clinic(clinic_slug)
        async with tenant_session(clinic.id) as session:
            repo = DoctorRepository(session)
            branch_repo = BranchAssignmentRepository(session)
            rows, _ = await repo.search_directory(
                tenant_id=clinic.id, query_text=None, specialization=None, branch_id=branch_id, limit=100, offset=0
            )
            items = []
            for user, profile in rows:
                branch_ids = await branch_repo.get_branch_ids(user.id)
                items.append(
                    PublicDoctorSummary(
                        user_id=user.id, first_name=user.first_name, last_name=user.last_name,
                        specialization=profile.specialization, consultation_fee=profile.consultation_fee,
                        slot_duration_minutes=profile.slot_duration_minutes, branch_ids=branch_ids,
                    )
                )
            return items

    async def list_slots(self, *, clinic_slug: str, doctor_id: uuid.UUID, target_date: date) -> PublicSlotsResponse:
        clinic = await _resolve_clinic(clinic_slug)
        async with tenant_session(clinic.id) as session:
            found = await DoctorRepository(session).get_user_and_profile(doctor_id)
            if found is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{doctor_id}' does not exist")
            _, profile = found
            slots = await list_available_slots(
                session, doctor_id=doctor_id, target_date=target_date,
                slot_duration_minutes=profile.slot_duration_minutes, clinic_timezone=clinic.timezone,
            )
            return PublicSlotsResponse(
                date=target_date,
                slots=[PublicSlot(scheduled_at=s, duration_minutes=profile.slot_duration_minutes) for s in slots],
            )

    async def book(self, *, clinic_slug: str, payload: PublicBookingRequest) -> PublicBookingResponse:
        clinic = await _resolve_clinic(clinic_slug)

        if payload.request_prepayment and payload.prepayment_amount is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "prepayment_amount is required when request_prepayment is true")

        async with tenant_session(clinic.id) as session:
            found = await DoctorRepository(session).get_user_and_profile(payload.doctor_id)
            if found is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{payload.doctor_id}' does not exist")
            _, doctor_profile = found
            duration_minutes = doctor_profile.slot_duration_minutes

            await validate_and_lock_slot(
                session, doctor_id=payload.doctor_id, branch_id=payload.branch_id,
                scheduled_at=payload.scheduled_at, duration_minutes=duration_minutes,
            )

            patient_repo = PatientRepository(session)
            patient = await patient_repo.find_by_phone(tenant_id=clinic.id, phone=payload.phone)
            if patient is None:
                # Same up-to-5-attempts MRN-collision retry as
                # PatientService.create_patient/AuthService._provision_patient_from_phone
                # — duplicated rather than imported, matching this
                # codebase's "each module keeps its own small helpers,
                # cross-module reach stays at the Repository level"
                # precedent (LeadService.convert_lead established this
                # first).
                for _ in range(5):
                    mrn = await patient_repo.next_mrn_candidate(tenant_id=clinic.id)
                    try:
                        patient = await patient_repo.create(
                            tenant_id=clinic.id, mrn=mrn, first_name=payload.first_name, last_name=payload.last_name,
                            phone=payload.phone, email=payload.email,
                        )
                        break
                    except IntegrityError:
                        continue
                if patient is None:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT, "Could not generate a unique medical record number — please retry"
                    )
                await record_audit(
                    session, tenant_id=clinic.id, actor_user_id=None, actor_role="PUBLIC",
                    action="patient.public_self_register", entity_type="patient", entity_id=patient.id,
                    before=None, after={"mrn": patient.mrn, "phone": payload.phone},
                )

            payment_status = AppointmentPaymentStatus.PENDING if payload.request_prepayment else AppointmentPaymentStatus.NOT_REQUIRED
            appointment = await AppointmentRepository(session).create(
                tenant_id=clinic.id, branch_id=payload.branch_id, patient_id=patient.id, doctor_id=payload.doctor_id,
                source=AppointmentSource.ONLINE, scheduled_at=payload.scheduled_at, duration_minutes=duration_minutes,
                notes=None, payment_status=payment_status,
            )

            gateway_order_info: PublicGatewayOrderInfo | None = None
            if payload.request_prepayment:
                assert payload.prepayment_amount is not None
                adapter = get_payment_gateway_adapter()
                gateway_order = await adapter.create_order(
                    amount=payload.prepayment_amount, currency="INR", receipt=str(appointment.id)
                )
                await PaymentGatewayOrderRepository(session).create(
                    tenant_id=clinic.id, appointment_id=appointment.id, provider=gateway_order.provider,
                    provider_order_id=gateway_order.order_id, amount=payload.prepayment_amount, currency="INR",
                )
                gateway_order_info = PublicGatewayOrderInfo(
                    provider=gateway_order.provider, order_id=gateway_order.order_id, amount=payload.prepayment_amount,
                    currency="INR", key_id=settings.razorpay_key_id,
                )

            await record_audit(
                session, tenant_id=clinic.id, actor_user_id=None, actor_role="PUBLIC",
                action="appointment.public_book", entity_type="appointment", entity_id=appointment.id,
                before=None, after={"scheduled_at": payload.scheduled_at.isoformat(), "payment_status": payment_status.value},
            )
            await dispatch_notification(
                session, tenant_id=clinic.id, template_key="APPOINTMENT_BOOKED", channel=CommChannel.WHATSAPP,
                patient_id=patient.id, context={"appointment_time": payload.scheduled_at.isoformat()},
            )

            return PublicBookingResponse(
                appointment_id=appointment.id, patient_id=patient.id, scheduled_at=appointment.scheduled_at,
                duration_minutes=appointment.duration_minutes, status=appointment.status.value,
                payment_status=appointment.payment_status.value, gateway_order=gateway_order_info,
            )

    async def retry_payment(self, *, clinic_slug: str, appointment_id: uuid.UUID, phone: str) -> PublicGatewayOrderInfo:
        """Phase 2 (Master Handoff item 5, "retry states") — a fresh
        gateway order for a booking whose prepayment is still PENDING (the
        patient never completed checkout) or FAILED (the gateway declined
        it) — never for CONFIRMED/REFUNDED/NOT_REQUIRED, and never for a
        CANCELLED appointment. `phone` is a lightweight ownership check —
        there's no account/session to authenticate this caller against,
        same "existence-hiding" 404 convention as every other row-scoped
        read in this codebase for a genuine mismatch."""
        clinic = await _resolve_clinic(clinic_slug)
        not_found = HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")

        async with tenant_session(clinic.id) as session:
            appointment_repo = AppointmentRepository(session)
            appointment = await appointment_repo.get_by_id(appointment_id)
            if appointment is None:
                raise not_found

            patient = await PatientRepository(session).get_by_id(appointment.patient_id)
            if patient is None or patient.phone != phone:
                raise not_found

            if appointment.payment_status not in (AppointmentPaymentStatus.PENDING, AppointmentPaymentStatus.FAILED):
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"This booking's payment is {appointment.payment_status.value}, not retryable"
                )

            order_repo = PaymentGatewayOrderRepository(session)
            previous_order = await order_repo.get_latest_for_appointment(appointment_id)
            amount = Decimal(str(previous_order.amount)) if previous_order is not None else None
            if amount is None:
                raise HTTPException(status.HTTP_409_CONFLICT, "No prior payment order found to retry")

            adapter = get_payment_gateway_adapter()
            gateway_order = await adapter.create_order(amount=amount, currency="INR", receipt=str(appointment.id))
            await order_repo.create(
                tenant_id=clinic.id, appointment_id=appointment.id, provider=gateway_order.provider,
                provider_order_id=gateway_order.order_id, amount=amount, currency="INR",
            )
            await appointment_repo.set_payment_status(appointment.id, payment_status=AppointmentPaymentStatus.PENDING)
            await record_audit(
                session, tenant_id=clinic.id, actor_user_id=None, actor_role="PUBLIC",
                action="appointment.payment_retry", entity_type="appointment", entity_id=appointment.id,
                before={"payment_status": appointment.payment_status.value}, after={"payment_status": "PENDING"},
            )
            return PublicGatewayOrderInfo(
                provider=gateway_order.provider, order_id=gateway_order.order_id, amount=amount,
                currency="INR", key_id=settings.razorpay_key_id,
            )
