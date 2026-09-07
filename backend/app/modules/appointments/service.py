"""Appointments business logic: booking (Owner/Receptionist for any
patient, Patient for themselves), search/read (Owner/Receptionist/Nurse
tenant-wide, Doctor scoped to their own schedule), reschedule, and cancel.
See PRD-ARCHITECTURE.md §5.1 (steps 1-2), §3 (permission matrix row
"Appointment booking (staff-side)" / "Online booking (patient-side)").

"Slot availability is derived from doctor working hours + existing
appointments, not a separately maintained calendar" (PRD §5.1 step 1) —
`_validate_slot` is that single source of truth, called by every path that
creates or moves an appointment (create, create_my, reschedule,
reschedule_my), so the same rules apply everywhere a slot is chosen.
"""

import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.appointments.models import Appointment, AppointmentSource, AppointmentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.schemas import (
    AppointmentCreateRequest,
    AppointmentListResponse,
    AppointmentRescheduleRequest,
    AppointmentSummary,
    MyAppointmentCreateRequest,
)
from app.modules.audit.service import record as record_audit
from app.modules.auth.models import UserStatus
from app.modules.doctors.repository import DoctorRepository
from app.modules.notifications.models import CommChannel
from app.modules.notifications.service import dispatch_notification
from app.modules.patients.repository import PatientRepository
from app.modules.tenancy.repository import BranchRepository
from app.modules.tenancy.schemas import WorkingHours

_WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class AppointmentService:
    async def _validate_slot(
        self,
        session,
        *,
        doctor_id: uuid.UUID,
        branch_id: uuid.UUID,
        scheduled_at: datetime,
        duration_minutes: int,
        exclude_appointment_id: uuid.UUID | None = None,
    ) -> None:
        if await BranchRepository(session).get_by_id(branch_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{branch_id}' does not exist")

        found = await DoctorRepository(session).get_user_and_profile(doctor_id)
        if found is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{doctor_id}' does not exist")
        doctor_user, doctor_profile = found
        if doctor_user.status != UserStatus.ACTIVE:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Doctor is not currently available for booking")

        end_at = scheduled_at + timedelta(minutes=duration_minutes)
        if end_at.date() != scheduled_at.date():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Appointment cannot span midnight")

        working_hours = WorkingHours.model_validate(doctor_profile.working_hours or {})
        day_hours = getattr(working_hours, _WEEKDAY_CODES[scheduled_at.weekday()])
        if day_hours is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Doctor is not available on the requested day")

        open_time = time.fromisoformat(day_hours.open)
        close_time = time.fromisoformat(day_hours.close)
        if scheduled_at.time() < open_time or end_at.time() > close_time:
            raise HTTPException(status.HTTP_409_CONFLICT, "Requested time is outside the doctor's working hours")

        repo = AppointmentRepository(session)
        if await repo.has_overlap(
            doctor_id=doctor_id, scheduled_at=scheduled_at, duration_minutes=duration_minutes, exclude_appointment_id=exclude_appointment_id
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "Doctor already has an appointment at this time")

    async def _resolve_own_patient_id(self, session, *, user_id: uuid.UUID) -> uuid.UUID:
        patient = await PatientRepository(session).get_by_user_id(user_id)
        if patient is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No patient record is linked to this account")
        return patient.id

    async def _create(
        self,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        branch_id: uuid.UUID,
        doctor_id: uuid.UUID,
        scheduled_at: datetime,
        duration_minutes: int,
        notes: str | None,
        source: AppointmentSource,
        actor_user_id: uuid.UUID,
        actor_role: str,
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            await self._validate_slot(
                session, doctor_id=doctor_id, branch_id=branch_id, scheduled_at=scheduled_at, duration_minutes=duration_minutes
            )
            appointment = await AppointmentRepository(session).create(
                tenant_id=tenant_id,
                branch_id=branch_id,
                patient_id=patient_id,
                doctor_id=doctor_id,
                source=source,
                scheduled_at=scheduled_at,
                duration_minutes=duration_minutes,
                notes=notes,
            )
            summary = AppointmentSummary.model_validate(appointment)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="appointment.create",
                entity_type="appointment",
                entity_id=appointment.id,
                before=None,
                after=summary.model_dump(mode="json"),
            )
            # Outbox integration (migration 0024) — queues a stubbed
            # reminder through the shared dispatcher; a clinic-configured
            # APPOINTMENT_BOOKED template applies if one is active, else a
            # built-in default body.
            await dispatch_notification(
                session, tenant_id=tenant_id, template_key="APPOINTMENT_BOOKED", channel=CommChannel.WHATSAPP,
                patient_id=patient_id, context={"appointment_time": scheduled_at.isoformat()},
            )
            return summary

    async def create_appointment(
        self, *, tenant_id: uuid.UUID, payload: AppointmentCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        return await self._create(
            tenant_id=tenant_id,
            patient_id=payload.patient_id,
            branch_id=payload.branch_id,
            doctor_id=payload.doctor_id,
            scheduled_at=payload.scheduled_at,
            duration_minutes=payload.duration_minutes,
            notes=payload.notes,
            source=AppointmentSource.RECEPTIONIST,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )

    async def create_my_appointment(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: MyAppointmentCreateRequest, actor_role: str
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            patient_id = await self._resolve_own_patient_id(session, user_id=user_id)
        return await self._create(
            tenant_id=tenant_id,
            patient_id=patient_id,
            branch_id=payload.branch_id,
            doctor_id=payload.doctor_id,
            scheduled_at=payload.scheduled_at,
            duration_minutes=payload.duration_minutes,
            notes=payload.notes,
            source=AppointmentSource.ONLINE,
            actor_user_id=user_id,
            actor_role=actor_role,
        )

    async def search_appointments(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_role: str,
        actor_user_id: uuid.UUID,
        patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        branch_id: uuid.UUID | None,
        status_filter: AppointmentStatus | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> AppointmentListResponse:
        # Doctor's "R (own)" access (PRD §3) is enforced here, not by a
        # separate permission code — same row-level-scoping pattern already
        # used for patients.view_emr. Any doctor_id the caller passed is
        # overridden, not merely validated, so a Doctor can never see past
        # their own schedule by supplying someone else's id.
        effective_doctor_id = actor_user_id if actor_role == "DOCTOR" else doctor_id

        async with tenant_session(tenant_id) as session:
            appointments, total = await AppointmentRepository(session).search(
                tenant_id=tenant_id,
                patient_id=patient_id,
                doctor_id=effective_doctor_id,
                branch_id=branch_id,
                status=status_filter,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
            return AppointmentListResponse(
                items=[AppointmentSummary.model_validate(a) for a in appointments], total=total, limit=limit, offset=offset
            )

    async def get_my_appointments(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> AppointmentListResponse:
        async with tenant_session(tenant_id) as session:
            patient_id = await self._resolve_own_patient_id(session, user_id=user_id)
            appointments, total = await AppointmentRepository(session).search(
                tenant_id=tenant_id,
                patient_id=patient_id,
                doctor_id=None,
                branch_id=None,
                status=None,
                date_from=None,
                date_to=None,
                limit=limit,
                offset=offset,
            )
            return AppointmentListResponse(
                items=[AppointmentSummary.model_validate(a) for a in appointments], total=total, limit=limit, offset=offset
            )

    async def get_appointment(
        self, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            appointment = await AppointmentRepository(session).get_by_id(appointment_id)
            if appointment is None or (actor_role == "DOCTOR" and appointment.doctor_id != actor_user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            return AppointmentSummary.model_validate(appointment)

    async def _reschedule(
        self, session, *, tenant_id: uuid.UUID, appointment: Appointment, payload: AppointmentRescheduleRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        if appointment.status != AppointmentStatus.SCHEDULED:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot reschedule an appointment with status {appointment.status.value}")

        new_scheduled_at = payload.scheduled_at or appointment.scheduled_at
        new_duration = payload.duration_minutes or appointment.duration_minutes
        new_doctor_id = payload.doctor_id or appointment.doctor_id
        new_branch_id = payload.branch_id or appointment.branch_id

        await self._validate_slot(
            session,
            doctor_id=new_doctor_id,
            branch_id=new_branch_id,
            scheduled_at=new_scheduled_at,
            duration_minutes=new_duration,
            exclude_appointment_id=appointment.id,
        )
        before = AppointmentSummary.model_validate(appointment)
        changes = payload.model_dump(exclude_unset=True)
        repo = AppointmentRepository(session)
        await repo.reschedule(appointment.id, **changes)
        updated = await repo.get_by_id(appointment.id)
        assert updated is not None
        after = AppointmentSummary.model_validate(updated)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="appointment.reschedule",
            entity_type="appointment",
            entity_id=appointment.id,
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
        )
        return after

    async def reschedule_appointment(
        self, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID, payload: AppointmentRescheduleRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            appointment = await AppointmentRepository(session).get_by_id(appointment_id)
            if appointment is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            return await self._reschedule(
                session, tenant_id=tenant_id, appointment=appointment, payload=payload, actor_user_id=actor_user_id, actor_role=actor_role
            )

    async def reschedule_my_appointment(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, appointment_id: uuid.UUID, payload: AppointmentRescheduleRequest
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            patient_id = await self._resolve_own_patient_id(session, user_id=user_id)
            appointment = await AppointmentRepository(session).get_by_id(appointment_id)
            if appointment is None or appointment.patient_id != patient_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            return await self._reschedule(
                session, tenant_id=tenant_id, appointment=appointment, payload=payload, actor_user_id=user_id, actor_role="PATIENT"
            )

    async def _cancel(
        self, session, *, tenant_id: uuid.UUID, appointment: Appointment, reason: str, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Appointment is already {appointment.status.value}")

        before = AppointmentSummary.model_validate(appointment)
        repo = AppointmentRepository(session)
        await repo.cancel(appointment.id, reason=reason, cancelled_by=actor_user_id)
        updated = await repo.get_by_id(appointment.id)
        assert updated is not None
        after = AppointmentSummary.model_validate(updated)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="appointment.cancel",
            entity_type="appointment",
            entity_id=appointment.id,
            before=before.model_dump(mode="json"),
            after=after.model_dump(mode="json"),
        )
        return after

    async def cancel_appointment(
        self, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID, reason: str, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            appointment = await AppointmentRepository(session).get_by_id(appointment_id)
            if appointment is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            return await self._cancel(
                session, tenant_id=tenant_id, appointment=appointment, reason=reason, actor_user_id=actor_user_id, actor_role=actor_role
            )

    async def cancel_my_appointment(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, appointment_id: uuid.UUID, reason: str
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            patient_id = await self._resolve_own_patient_id(session, user_id=user_id)
            appointment = await AppointmentRepository(session).get_by_id(appointment_id)
            if appointment is None or appointment.patient_id != patient_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            return await self._cancel(session, tenant_id=tenant_id, appointment=appointment, reason=reason, actor_user_id=user_id, actor_role="PATIENT")
