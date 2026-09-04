"""CRM & Follow-ups business logic — see app/modules/crm/models.py's
module docstring and PRD-ARCHITECTURE.md §5.6/§20.

Row-scoping: Owner/Receptionist (`crm.manage`) are tenant-wide; Doctor
(also `crm.manage`, by direct instruction — see migration 0019's
docstring) is scoped to `doctor_id == caller`, the same shared-permission-
code-plus-service-scoping pattern Consultation/Prescription established.
Creating a follow-up as a Doctor silently forces `doctor_id` to the
caller, the same "override, don't merely validate" pattern
`AppointmentService` uses for Doctor's own schedule.

`FollowUpRepository.sweep_overdue` runs before every read in this service
(search and get) so a caller never sees a `PENDING`/`SENT` row whose
`due_at` has already passed without it being reported as `OVERDUE` — see
migration 0019's docstring for why this is lazy-on-read rather than a
scheduled job.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import update

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.checkin.repository import EncounterRepository
from app.modules.crm.models import CommStatus, CommunicationLog, FollowUp, FollowUpStatus
from app.modules.crm.repository import CommunicationLogRepository, FollowUpRepository
from app.modules.crm.schemas import (
    CommunicationLogSummary,
    FollowUpCreateRequest,
    FollowUpListResponse,
    FollowUpStatusUpdateRequest,
    FollowUpSummary,
)
from app.modules.doctors.repository import DoctorRepository
from app.modules.patients.repository import PatientRepository

_ALLOWED_TRANSITIONS: dict[FollowUpStatus, set[FollowUpStatus]] = {
    FollowUpStatus.PENDING: {FollowUpStatus.SENT, FollowUpStatus.CONFIRMED, FollowUpStatus.CANCELLED},
    FollowUpStatus.SENT: {FollowUpStatus.CONFIRMED, FollowUpStatus.CANCELLED},
    FollowUpStatus.OVERDUE: {FollowUpStatus.SENT, FollowUpStatus.CONFIRMED, FollowUpStatus.CANCELLED},
    FollowUpStatus.CONFIRMED: set(),
    FollowUpStatus.CANCELLED: set(),
}


def _own_scoped_doctor_filter(actor_role: str, actor_user_id: uuid.UUID, requested_doctor_id: uuid.UUID | None) -> uuid.UUID | None:
    return actor_user_id if actor_role == "DOCTOR" else requested_doctor_id


def _to_summary(follow_up: FollowUp) -> FollowUpSummary:
    return FollowUpSummary(
        id=follow_up.id, tenant_id=follow_up.tenant_id, patient_id=follow_up.patient_id, doctor_id=follow_up.doctor_id,
        encounter_id=follow_up.encounter_id, due_at=follow_up.due_at, status=follow_up.status.value, reason=follow_up.reason,
        created_by=follow_up.created_by, created_at=follow_up.created_at, updated_at=follow_up.updated_at,
        reminder=CommunicationLogSummary.model_validate(follow_up.reminder) if follow_up.reminder else None,
    )


class FollowUpService:
    async def create_follow_up(self, *, tenant_id: uuid.UUID, payload: FollowUpCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> FollowUpSummary:
        async with tenant_session(tenant_id) as session:
            if await PatientRepository(session).get_by_id(payload.patient_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Patient '{payload.patient_id}' does not exist")

            doctor_id = actor_user_id if actor_role == "DOCTOR" else payload.doctor_id
            if doctor_id is not None and await DoctorRepository(session).get_user_and_profile(doctor_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{doctor_id}' does not exist")

            if payload.encounter_id is not None and await EncounterRepository(session).get_by_id(payload.encounter_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")

            # Task 3: a stubbed outbox entry — no real SMS/WhatsApp send.
            reminder = await CommunicationLogRepository(session).create(
                tenant_id=tenant_id, patient_id=payload.patient_id, channel=payload.channel, status=CommStatus.QUEUED
            )

            follow_up_repo = FollowUpRepository(session)
            follow_up = await follow_up_repo.create(
                tenant_id=tenant_id, patient_id=payload.patient_id, doctor_id=doctor_id, encounter_id=payload.encounter_id,
                due_at=payload.due_at, reason=payload.reason, reminder_log_id=reminder.id, created_by=actor_user_id,
            )
            full = await follow_up_repo.get_by_id(follow_up.id)
            assert full is not None
            summary = _to_summary(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="follow_up.create", entity_type="follow_up", entity_id=follow_up.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_status(self, *, tenant_id: uuid.UUID, follow_up_id: uuid.UUID, payload: FollowUpStatusUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> FollowUpSummary:
        try:
            new_status = FollowUpStatus(payload.status)
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid status '{payload.status}'")

        async with tenant_session(tenant_id) as session:
            repo = FollowUpRepository(session)
            await repo.sweep_overdue(tenant_id=tenant_id)
            follow_up = await repo.get_by_id(follow_up_id)
            if follow_up is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found")
            if actor_role == "DOCTOR" and follow_up.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot update another doctor's follow-up")
            if new_status not in _ALLOWED_TRANSITIONS[follow_up.status]:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move a follow-up from {follow_up.status.value} to {new_status.value}")

            before_status = follow_up.status
            await repo.update_fields(follow_up.id, status=new_status)

            # Keep the stubbed reminder outbox entry in sync — "when
            # patient responds" (task 2) implies the reminder was
            # actually sent first.
            if new_status == FollowUpStatus.SENT and follow_up.reminder_log_id is not None:
                await session.execute(
                    update(CommunicationLog).where(CommunicationLog.id == follow_up.reminder_log_id).values(status=CommStatus.SENT, sent_at=datetime.now(timezone.utc))
                )

            updated = await repo.get_by_id(follow_up.id)
            assert updated is not None
            summary = _to_summary(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="follow_up.status_change", entity_type="follow_up", entity_id=follow_up.id,
                before={"status": before_status.value}, after={"status": new_status.value},
            )
            return summary

    async def search_follow_ups(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, doctor_id: uuid.UUID | None, status_filter: FollowUpStatus | None,
        due_from: datetime | None, due_to: datetime | None, overdue_only: bool, actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int,
    ) -> FollowUpListResponse:
        effective_doctor_id = _own_scoped_doctor_filter(actor_role, actor_user_id, doctor_id)
        async with tenant_session(tenant_id) as session:
            repo = FollowUpRepository(session)
            await repo.sweep_overdue(tenant_id=tenant_id)
            rows, total = await repo.search(
                tenant_id=tenant_id, patient_id=patient_id, doctor_id=effective_doctor_id, status=status_filter,
                due_from=due_from, due_to=due_to, overdue_only=overdue_only, limit=limit, offset=offset,
            )
            return FollowUpListResponse(items=[_to_summary(f) for f in rows], total=total, limit=limit, offset=offset)

    async def get_follow_up(self, *, tenant_id: uuid.UUID, follow_up_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> FollowUpSummary:
        async with tenant_session(tenant_id) as session:
            repo = FollowUpRepository(session)
            await repo.sweep_overdue(tenant_id=tenant_id)
            follow_up = await repo.get_by_id(follow_up_id)
            if follow_up is None or (actor_role == "DOCTOR" and follow_up.doctor_id != actor_user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found")
            return _to_summary(follow_up)
