import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.appointments.models import Appointment, AppointmentStatus

_INACTIVE_STATUSES = (AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW)


class AppointmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID | None,
        source,
        scheduled_at: datetime,
        duration_minutes: int,
        notes: str | None,
        status: AppointmentStatus | None = None,
    ) -> Appointment:
        appointment = Appointment(
            tenant_id=tenant_id,
            branch_id=branch_id,
            patient_id=patient_id,
            doctor_id=doctor_id,
            source=source,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            notes=notes,
        )
        if status is not None:
            appointment.status = status
        self._session.add(appointment)
        await self._session.flush()
        return appointment

    async def get_by_id(self, appointment_id: uuid.UUID) -> Appointment | None:
        result = await self._session.execute(select(Appointment).where(Appointment.id == appointment_id))
        return result.scalar_one_or_none()

    async def has_overlap(
        self, *, doctor_id: uuid.UUID, scheduled_at: datetime, duration_minutes: int, exclude_appointment_id: uuid.UUID | None = None
    ) -> bool:
        """Two intervals [a_start, a_end) and [b_start, b_end) overlap iff
        a_start < b_end AND b_start < a_end. Cancelled/no-show appointments
        don't hold the slot."""
        new_end = scheduled_at + timedelta(minutes=duration_minutes)
        existing_end_expr = Appointment.scheduled_at + func.make_interval(0, 0, 0, 0, 0, Appointment.duration_minutes)

        filters = [
            Appointment.doctor_id == doctor_id,
            Appointment.status.notin_(_INACTIVE_STATUSES),
            Appointment.scheduled_at < new_end,
            existing_end_expr > scheduled_at,
        ]
        if exclude_appointment_id:
            filters.append(Appointment.id != exclude_appointment_id)

        result = await self._session.execute(select(func.count()).select_from(Appointment).where(*filters))
        return result.scalar_one() > 0

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        branch_id: uuid.UUID | None,
        status: AppointmentStatus | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Appointment], int]:
        filters = [Appointment.tenant_id == tenant_id]
        if patient_id:
            filters.append(Appointment.patient_id == patient_id)
        if doctor_id:
            filters.append(Appointment.doctor_id == doctor_id)
        if branch_id:
            filters.append(Appointment.branch_id == branch_id)
        if status:
            filters.append(Appointment.status == status)
        if date_from:
            filters.append(Appointment.scheduled_at >= date_from)
        if date_to:
            filters.append(Appointment.scheduled_at <= date_to)

        count_result = await self._session.execute(select(func.count()).select_from(Appointment).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Appointment).where(*filters).order_by(Appointment.scheduled_at.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

    async def reschedule(self, appointment_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Appointment).where(Appointment.id == appointment_id).values(**fields))

    async def update_status(self, appointment_id: uuid.UUID, *, status: AppointmentStatus) -> None:
        """Used by the Check-in module (CHECKED_IN, NO_SHOW) — distinct
        from `reschedule`, which is about moving a SCHEDULED slot, not a
        day-of status transition."""
        await self._session.execute(
            update(Appointment).where(Appointment.id == appointment_id).values(status=status, updated_at=datetime.now(timezone.utc))
        )

    async def cancel(self, appointment_id: uuid.UUID, *, reason: str, cancelled_by: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(Appointment)
            .where(Appointment.id == appointment_id)
            .values(
                status=AppointmentStatus.CANCELLED,
                cancelled_reason=reason,
                cancelled_by=cancelled_by,
                cancelled_at=now,
                updated_at=now,
            )
        )
