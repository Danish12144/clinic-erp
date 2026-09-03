"""Walk-in registration, check-in, and queue/token issuance business logic
— see app/modules/checkin/models.py's module docstring and
PRD-ARCHITECTURE.md §5.1 (steps 3/5/6).

Both `register_walk_in` and `check_in_appointment` produce the same shape
of result (an Appointment in CHECKED_IN status, its Encounter, and the
QueueToken issued for it) via the shared `_check_in` — a walk-in just
creates the Appointment first instead of it already existing.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.appointments.models import Appointment, AppointmentSource, AppointmentStatus
from app.modules.appointments.repository import AppointmentRepository
from app.modules.appointments.schemas import AppointmentSummary
from app.modules.audit.service import record as record_audit
from app.modules.auth.models import UserStatus
from app.modules.checkin.models import EncounterStatus, QueueTokenStatus
from app.modules.checkin.repository import EncounterRepository, QueueTokenRepository
from app.modules.checkin.schemas import (
    CheckInResult,
    EncounterCancelRequest,
    EncounterListResponse,
    EncounterSummary,
    QueueListResponse,
    QueueTokenSummary,
    WalkInRequest,
)
from app.modules.doctors.repository import DoctorRepository
from app.modules.patients.repository import PatientRepository
from app.modules.tenancy.repository import BranchRepository

# WAITING -> CALLED -> IN_PROGRESS -> DONE, with SKIPPED/NO_SHOW as side
# exits and SKIPPED able to re-enter the line (PRD §5.1 step 6's token
# status machine; the SKIPPED re-entry points aren't in the PRD's diagram
# but are the obvious front-desk operation "put them back in/re-call them").
_ALLOWED_QUEUE_TRANSITIONS: dict[QueueTokenStatus, set[QueueTokenStatus]] = {
    QueueTokenStatus.WAITING: {QueueTokenStatus.CALLED, QueueTokenStatus.SKIPPED},
    QueueTokenStatus.CALLED: {QueueTokenStatus.IN_PROGRESS, QueueTokenStatus.NO_SHOW, QueueTokenStatus.SKIPPED},
    QueueTokenStatus.SKIPPED: {QueueTokenStatus.CALLED, QueueTokenStatus.WAITING},
    QueueTokenStatus.IN_PROGRESS: {QueueTokenStatus.DONE},
    QueueTokenStatus.DONE: set(),
    QueueTokenStatus.NO_SHOW: set(),
}


class CheckInService:
    async def _check_in(
        self,
        session,
        *,
        tenant_id: uuid.UUID,
        appointment: Appointment,
        actor_user_id: uuid.UUID,
        actor_role: str,
    ) -> CheckInResult:
        encounter = await EncounterRepository(session).create(
            tenant_id=tenant_id, branch_id=appointment.branch_id, appointment_id=appointment.id, patient_id=appointment.patient_id
        )
        encounter_summary = EncounterSummary.model_validate(encounter)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="encounter.check_in",
            entity_type="encounter",
            entity_id=encounter.id,
            before=None,
            after=encounter_summary.model_dump(mode="json"),
        )

        token = await QueueTokenRepository(session).issue(
            tenant_id=tenant_id, branch_id=appointment.branch_id, encounter_id=encounter.id, doctor_id=appointment.doctor_id
        )
        token_summary = QueueTokenSummary.model_validate(token)
        await record_audit(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="queue_token.issue",
            entity_type="queue_token",
            entity_id=token.id,
            before=None,
            after=token_summary.model_dump(mode="json"),
        )

        return CheckInResult(
            appointment=AppointmentSummary.model_validate(appointment), encounter=encounter_summary, queue_token=token_summary
        )

    async def register_walk_in(
        self, *, tenant_id: uuid.UUID, payload: WalkInRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> CheckInResult:
        async with tenant_session(tenant_id) as session:
            if await BranchRepository(session).get_by_id(payload.branch_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{payload.branch_id}' does not exist")
            if await PatientRepository(session).get_by_id(payload.patient_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Patient '{payload.patient_id}' does not exist")
            if payload.doctor_id is not None:
                found = await DoctorRepository(session).get_user_and_profile(payload.doctor_id)
                if found is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Doctor '{payload.doctor_id}' does not exist")
                if found[0].status != UserStatus.ACTIVE:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Doctor is not currently available")

            # Retroactively created per PRD §5.1 step 3 ("an
            # Appointment{source=WALK_IN, status=CHECKED_IN} is created
            # retroactively so downstream reporting doesn't need a separate
            # 'visit without appointment' concept") — scheduled_at is the
            # walk-in time itself, not a future slot, so the future-dated
            # validation appointments booking uses does not apply here.
            appointment = await AppointmentRepository(session).create(
                tenant_id=tenant_id,
                branch_id=payload.branch_id,
                patient_id=payload.patient_id,
                doctor_id=payload.doctor_id,
                source=AppointmentSource.WALK_IN,
                scheduled_at=datetime.now(timezone.utc),
                duration_minutes=15,
                notes=payload.notes,
                status=AppointmentStatus.CHECKED_IN,
            )
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="appointment.walk_in",
                entity_type="appointment",
                entity_id=appointment.id,
                before=None,
                after=AppointmentSummary.model_validate(appointment).model_dump(mode="json"),
            )

            return await self._check_in(session, tenant_id=tenant_id, appointment=appointment, actor_user_id=actor_user_id, actor_role=actor_role)

    async def check_in_appointment(
        self, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> CheckInResult:
        async with tenant_session(tenant_id) as session:
            repo = AppointmentRepository(session)
            appointment = await repo.get_by_id(appointment_id)
            if appointment is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            if appointment.status != AppointmentStatus.SCHEDULED:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot check in an appointment with status {appointment.status.value}")

            before = AppointmentSummary.model_validate(appointment)
            await repo.update_status(appointment.id, status=AppointmentStatus.CHECKED_IN)
            appointment = await repo.get_by_id(appointment.id)
            assert appointment is not None
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="appointment.check_in",
                entity_type="appointment",
                entity_id=appointment.id,
                before=before.model_dump(mode="json"),
                after=AppointmentSummary.model_validate(appointment).model_dump(mode="json"),
            )

            return await self._check_in(session, tenant_id=tenant_id, appointment=appointment, actor_user_id=actor_user_id, actor_role=actor_role)

    async def mark_no_show(
        self, *, tenant_id: uuid.UUID, appointment_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> AppointmentSummary:
        async with tenant_session(tenant_id) as session:
            repo = AppointmentRepository(session)
            appointment = await repo.get_by_id(appointment_id)
            if appointment is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
            if appointment.status != AppointmentStatus.SCHEDULED:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot mark no-show on an appointment with status {appointment.status.value}")

            before = AppointmentSummary.model_validate(appointment)
            await repo.update_status(appointment.id, status=AppointmentStatus.NO_SHOW)
            appointment = await repo.get_by_id(appointment.id)
            assert appointment is not None
            after = AppointmentSummary.model_validate(appointment)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="appointment.no_show",
                entity_type="appointment",
                entity_id=appointment.id,
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )
            return after

    async def search_encounters(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        status_filter: EncounterStatus | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> EncounterListResponse:
        async with tenant_session(tenant_id) as session:
            encounters, total = await EncounterRepository(session).search(
                tenant_id=tenant_id, branch_id=branch_id, patient_id=patient_id, status=status_filter, date_from=date_from, date_to=date_to, limit=limit, offset=offset
            )
            return EncounterListResponse(items=[EncounterSummary.model_validate(e) for e in encounters], total=total, limit=limit, offset=offset)

    async def get_encounter(self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID) -> EncounterSummary:
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
            return EncounterSummary.model_validate(encounter)

    async def cancel_encounter(
        self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID, payload: EncounterCancelRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> EncounterSummary:
        """Corrects a mistaken check-in (e.g. wrong patient checked in).
        Only an OPEN encounter can be cancelled — once a consultation has
        started (IN_CONSULTATION/COMPLETED, the future Consultation
        module's concern) front desk can no longer undo it here. Its
        QueueToken, if not already in a terminal state, moves to SKIPPED —
        the closest existing status to "this visit isn't happening," since
        the token state machine has no CANCELLED of its own."""
        async with tenant_session(tenant_id) as session:
            encounter_repo = EncounterRepository(session)
            encounter = await encounter_repo.get_by_id(encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
            if encounter.status != EncounterStatus.OPEN:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot cancel an encounter with status {encounter.status.value}")

            before = EncounterSummary.model_validate(encounter)
            await encounter_repo.update_status(encounter.id, status=EncounterStatus.CANCELLED)
            encounter = await encounter_repo.get_by_id(encounter.id)
            assert encounter is not None
            after = EncounterSummary.model_validate(encounter)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="encounter.cancel",
                entity_type="encounter",
                entity_id=encounter.id,
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )

            token_repo = QueueTokenRepository(session)
            token = await token_repo.get_by_encounter_id(encounter.id)
            if token is not None and token.status not in (QueueTokenStatus.DONE, QueueTokenStatus.NO_SHOW):
                await token_repo.update_status(token.id, status=QueueTokenStatus.SKIPPED)
                await record_audit(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    action="queue_token.status_change",
                    entity_type="queue_token",
                    entity_id=token.id,
                    before={"status": token.status.value},
                    after={"status": QueueTokenStatus.SKIPPED.value},
                )

            return after

    async def search_queue(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        status_filter: QueueTokenStatus | None,
        limit: int,
        offset: int,
    ) -> QueueListResponse:
        async with tenant_session(tenant_id) as session:
            tokens, total = await QueueTokenRepository(session).search(
                tenant_id=tenant_id, branch_id=branch_id, doctor_id=doctor_id, status=status_filter, token_date=None, limit=limit, offset=offset
            )
            return QueueListResponse(items=[QueueTokenSummary.model_validate(t) for t in tokens], total=total, limit=limit, offset=offset)

    async def call_next(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, doctor_id: uuid.UUID | None, actor_user_id: uuid.UUID, actor_role: str
    ) -> QueueTokenSummary:
        async with tenant_session(tenant_id) as session:
            repo = QueueTokenRepository(session)
            token = await repo.find_next_waiting(tenant_id=tenant_id, branch_id=branch_id, doctor_id=doctor_id)
            if token is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No patients waiting in this queue")

            now = datetime.now(timezone.utc)
            await repo.update_status(token.id, status=QueueTokenStatus.CALLED, called_at=now)
            token = await repo.get_by_id(token.id)
            assert token is not None
            summary = QueueTokenSummary.model_validate(token)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="queue_token.call",
                entity_type="queue_token",
                entity_id=token.id,
                before={"status": QueueTokenStatus.WAITING.value},
                after={"status": QueueTokenStatus.CALLED.value},
            )
            return summary

    async def update_token_status(
        self, *, tenant_id: uuid.UUID, token_id: uuid.UUID, new_status: QueueTokenStatus, actor_user_id: uuid.UUID, actor_role: str
    ) -> QueueTokenSummary:
        async with tenant_session(tenant_id) as session:
            repo = QueueTokenRepository(session)
            token = await repo.get_by_id(token_id)
            if token is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Queue token not found")
            if new_status not in _ALLOWED_QUEUE_TRANSITIONS[token.status]:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot move a token from {token.status.value} to {new_status.value}")

            before_status = token.status
            called_at = datetime.now(timezone.utc) if new_status == QueueTokenStatus.CALLED else None
            await repo.update_status(token.id, status=new_status, called_at=called_at)
            token = await repo.get_by_id(token.id)
            assert token is not None
            summary = QueueTokenSummary.model_validate(token)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="queue_token.status_change",
                entity_type="queue_token",
                entity_id=token.id,
                before={"status": before_status.value},
                after={"status": new_status.value},
            )
            return summary
