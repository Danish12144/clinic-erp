"""The single source of truth for "is this doctor+branch+time bookable" —
extracted out of `AppointmentService` into a free function (Phase 2,
Master Handoff item 1) specifically so the new public self-booking flow
(`app/modules/public/service.py`) can reuse the exact same validation and
concurrency guard `AppointmentService` itself uses, without one module's
Service calling another module's Service — this codebase's established
convention is that cross-module reach stays at the Repository/free-
function level (see `record_audit`/`issue_staff_invite`/
`dispatch_notification`, all free functions for the same reason: the
caller supplies its own already-open `tenant_session`, so everything
commits or rolls back together as one transaction).

`AppointmentService._validate_slot` is now a thin wrapper around
`validate_and_lock_slot` below — existing behavior, tests, and call sites
are unchanged; this is a pure refactor plus the new advisory lock.
"""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.modules.appointments.repository import AppointmentRepository
from app.modules.auth.models import UserStatus
from app.modules.doctors.repository import DoctorRepository
from app.modules.tenancy.repository import BranchRepository
from app.modules.tenancy.schemas import WorkingHours

_WEEKDAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


async def validate_and_lock_slot(
    session,
    *,
    doctor_id: uuid.UUID,
    branch_id: uuid.UUID,
    scheduled_at: datetime,
    duration_minutes: int,
    exclude_appointment_id: uuid.UUID | None = None,
) -> None:
    # Phase 2 (Master Handoff item 1) — serializes every slot validation +
    # booking for this doctor within this transaction, so two concurrent
    # requests for the same doctor+time can never both pass the overlap
    # check below before either has committed. See
    # AppointmentRepository.lock_doctor_for_booking's own docstring.
    await AppointmentRepository(session).lock_doctor_for_booking(doctor_id)

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

    # Pre-launch testing accommodation (Settings.appointment_enforce_
    # working_hours, default off): skip the doctor's declared window
    # entirely so booking/instant check-in isn't blocked outside a
    # doctor's configured hours during end-to-end testing — the
    # doctor-exists/branch-exists/overlap checks above and below still
    # apply either way. See that setting's own docstring.
    if get_settings().appointment_enforce_working_hours:
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


async def list_available_slots(
    session, *, doctor_id: uuid.UUID, target_date: date, slot_duration_minutes: int, clinic_timezone: str,
) -> list[datetime]:
    """The public booking widget's "slot availability engine" (Master
    Handoff item 1): every slot_duration_minutes-spaced start time within
    the doctor's working hours on `target_date` that doesn't overlap an
    existing non-cancelled/no-show appointment. Read-only preview — the
    real, race-safe guarantee is still `validate_and_lock_slot` at actual
    booking time (a slot returned here can still lose a concurrent race
    to another booking between this read and that later write; the
    advisory lock is what makes the *write* safe, not this list).

    `clinic_timezone` (`Clinic.timezone`, e.g. "Asia/Kolkata") matters
    because a doctor's `working_hours` are entered as local wall-clock
    strings ("09:00") — the returned datetimes carry that zone's real UTC
    offset, matching what `_validate_future`/`validate_and_lock_slot`
    already expect a client-submitted `scheduled_at` to look like (same
    "wall-clock, not normalized-to-UTC" comparison the working-hours check
    above already relies on)."""
    found = await DoctorRepository(session).get_user_and_profile(doctor_id)
    if found is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{doctor_id}' does not exist")
    doctor_user, doctor_profile = found
    if doctor_user.status != UserStatus.ACTIVE:
        return []

    working_hours = WorkingHours.model_validate(doctor_profile.working_hours or {})
    day_hours = getattr(working_hours, _WEEKDAY_CODES[target_date.weekday()])
    if day_hours is None:
        return []

    open_time = time.fromisoformat(day_hours.open)
    close_time = time.fromisoformat(day_hours.close)
    tz = ZoneInfo(clinic_timezone)

    day_start = datetime.combine(target_date, open_time, tzinfo=tz)
    day_end = datetime.combine(target_date, close_time, tzinfo=tz)

    repo = AppointmentRepository(session)
    candidates: list[datetime] = []
    cursor = day_start
    step = timedelta(minutes=slot_duration_minutes)
    while cursor + step <= day_end:
        candidates.append(cursor)
        cursor += step

    available: list[datetime] = []
    for candidate in candidates:
        if not await repo.has_overlap(doctor_id=doctor_id, scheduled_at=candidate, duration_minutes=slot_duration_minutes):
            available.append(candidate)
    return available
