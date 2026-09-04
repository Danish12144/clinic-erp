"""Consultation and Prescription business logic — see
app/modules/consultation/models.py's module docstring and
PRD-ARCHITECTURE.md §5.1.

Row-scoping convention used throughout (matches the PRD §3 matrix's
"F (own)"/read scoping already established for Appointments' Doctor rows):
a Doctor may only act on / see consultations and prescriptions where
`doctor_id == their own user id`; Owner and Nurse are tenant-wide,
unscoped (per the direct instruction recorded in migration 0013's
docstring). A write attempted against someone else's row is a 403 (the
caller has the permission bit but not the ownership); a single-record read
of someone else's row is a 404 (existence-hiding), same pattern
`AppointmentService.get_appointment` already uses for Doctor.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.checkin.models import EncounterStatus
from app.modules.checkin.repository import EncounterRepository
from app.modules.consultation.repository import ConsultationRepository, PrescriptionRepository
from app.modules.consultation.schemas import (
    ConsultationListResponse,
    ConsultationStartRequest,
    ConsultationSummary,
    ConsultationUpdateRequest,
    PrescriptionCreateRequest,
    PrescriptionListResponse,
    PrescriptionPrintView,
    PrescriptionSummary,
)
from app.modules.letterhead.schemas import LetterheadPrintMode
from app.modules.letterhead.service import LetterheadService
from app.modules.pharmacy.repository import MedicineRepository


def _own_scoped_doctor_filter(actor_role: str, actor_user_id: uuid.UUID, requested_doctor_id: uuid.UUID | None) -> uuid.UUID | None:
    return actor_user_id if actor_role == "DOCTOR" else requested_doctor_id


async def _validate_catalog_medicine_ids(session, *, items) -> None:
    """Added once the Pharmacy module (migration 0017) gave
    `medicine_id` somewhere real to point at — a caller-supplied
    `medicine_id` is trusted no further than any other foreign id, so
    each one is checked against the tenant's own catalog (RLS-scoped,
    same as everywhere else) before the prescription is created."""
    medicine_repo = MedicineRepository(session)
    for item in items:
        medicine_id = item.get("medicine_id")
        if medicine_id is not None and await medicine_repo.get_by_id(medicine_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Medicine '{medicine_id}' does not exist")


class ConsultationService:
    async def start_consultation(
        self, *, tenant_id: uuid.UUID, payload: ConsultationStartRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> ConsultationSummary:
        async with tenant_session(tenant_id) as session:
            encounter_repo = EncounterRepository(session)
            encounter = await encounter_repo.get_by_id(payload.encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")
            if encounter.status != EncounterStatus.OPEN:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot start a consultation on an encounter with status {encounter.status.value}")

            consult_repo = ConsultationRepository(session)
            if await consult_repo.get_by_encounter_id(encounter.id) is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "A consultation already exists for this encounter")

            consultation = await consult_repo.create(
                tenant_id=tenant_id, encounter_id=encounter.id, doctor_id=actor_user_id, chief_complaint=payload.chief_complaint
            )
            summary = ConsultationSummary.model_validate(consultation)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="consultation.start", entity_type="consultation", entity_id=consultation.id,
                before=None, after=summary.model_dump(mode="json"),
            )

            await encounter_repo.update_status(encounter.id, status=EncounterStatus.IN_CONSULTATION)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="encounter.status_change", entity_type="encounter", entity_id=encounter.id,
                before={"status": EncounterStatus.OPEN.value}, after={"status": EncounterStatus.IN_CONSULTATION.value},
            )
            return summary

    async def update_consultation(
        self, *, tenant_id: uuid.UUID, consultation_id: uuid.UUID, payload: ConsultationUpdateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> ConsultationSummary:
        async with tenant_session(tenant_id) as session:
            repo = ConsultationRepository(session)
            consultation = await repo.get_by_id(consultation_id)
            if consultation is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
            if actor_role == "DOCTOR" and consultation.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot edit another doctor's consultation")
            if consultation.ended_at is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Cannot edit a completed consultation")

            before = ConsultationSummary.model_validate(consultation)
            changes = payload.model_dump(exclude_unset=True)
            await repo.update_fields(consultation.id, **changes)
            updated = await repo.get_by_id(consultation.id)
            assert updated is not None
            after = ConsultationSummary.model_validate(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="consultation.update", entity_type="consultation", entity_id=consultation.id,
                before=before.model_dump(mode="json"), after=after.model_dump(mode="json"),
            )
            return after

    async def complete_consultation(
        self, *, tenant_id: uuid.UUID, consultation_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> ConsultationSummary:
        async with tenant_session(tenant_id) as session:
            consult_repo = ConsultationRepository(session)
            consultation = await consult_repo.get_by_id(consultation_id)
            if consultation is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
            if actor_role == "DOCTOR" and consultation.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot complete another doctor's consultation")
            if consultation.ended_at is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "Consultation is already completed")

            encounter_repo = EncounterRepository(session)
            encounter = await encounter_repo.get_by_id(consultation.encounter_id)
            assert encounter is not None
            if encounter.status != EncounterStatus.IN_CONSULTATION:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot complete a consultation while its encounter is {encounter.status.value}")

            await consult_repo.complete(consultation.id)
            updated = await consult_repo.get_by_id(consultation.id)
            assert updated is not None
            summary = ConsultationSummary.model_validate(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="consultation.complete", entity_type="consultation", entity_id=consultation.id,
                before={"ended_at": None}, after={"ended_at": summary.ended_at.isoformat()},
            )

            await encounter_repo.update_status(encounter.id, status=EncounterStatus.COMPLETED)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="encounter.status_change", entity_type="encounter", entity_id=encounter.id,
                before={"status": EncounterStatus.IN_CONSULTATION.value}, after={"status": EncounterStatus.COMPLETED.value},
            )
            return summary

    async def search_consultations(
        self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID | None, patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None, actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int,
    ) -> ConsultationListResponse:
        effective_doctor_id = _own_scoped_doctor_filter(actor_role, actor_user_id, doctor_id)
        async with tenant_session(tenant_id) as session:
            rows, total = await ConsultationRepository(session).search(
                tenant_id=tenant_id, encounter_id=encounter_id, patient_id=patient_id, doctor_id=effective_doctor_id, limit=limit, offset=offset
            )
            return ConsultationListResponse(items=[ConsultationSummary.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)

    async def get_consultation(self, *, tenant_id: uuid.UUID, consultation_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> ConsultationSummary:
        async with tenant_session(tenant_id) as session:
            consultation = await ConsultationRepository(session).get_by_id(consultation_id)
            if consultation is None or (actor_role == "DOCTOR" and consultation.doctor_id != actor_user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
            return ConsultationSummary.model_validate(consultation)


class PrescriptionService:
    async def issue_prescription(
        self, *, tenant_id: uuid.UUID, payload: PrescriptionCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> PrescriptionSummary:
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(payload.encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")

            consultation = await ConsultationRepository(session).get_by_encounter_id(encounter.id)
            if consultation is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A consultation must be started for this encounter before issuing a prescription")
            if actor_role == "DOCTOR" and consultation.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot issue a prescription for another doctor's consultation")

            items = [item.model_dump() for item in payload.items]
            await _validate_catalog_medicine_ids(session, items=items)
            prescription = await PrescriptionRepository(session).create_with_items(
                tenant_id=tenant_id, encounter_id=encounter.id, doctor_id=actor_user_id, items=items
            )
            full = await PrescriptionRepository(session).get_by_id(prescription.id)
            assert full is not None
            summary = PrescriptionSummary.model_validate(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="prescription.issue", entity_type="prescription", entity_id=prescription.id,
                before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def supersede_prescription(
        self, *, tenant_id: uuid.UUID, prescription_id: uuid.UUID, payload: PrescriptionCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> PrescriptionSummary:
        async with tenant_session(tenant_id) as session:
            repo = PrescriptionRepository(session)
            original = await repo.get_by_id(prescription_id)
            if original is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
            if actor_role == "DOCTOR" and original.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot supersede another doctor's prescription")
            if await repo.get_superseded_by(original.id) is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, "This prescription has already been superseded")

            items = [item.model_dump() for item in payload.items]
            await _validate_catalog_medicine_ids(session, items=items)
            new_prescription = await repo.create_with_items(
                tenant_id=tenant_id, encounter_id=original.encounter_id, doctor_id=actor_user_id, items=items,
                supersedes_prescription_id=original.id,
            )
            full = await repo.get_by_id(new_prescription.id)
            assert full is not None
            summary = PrescriptionSummary.model_validate(full)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="prescription.supersede", entity_type="prescription", entity_id=new_prescription.id,
                before={"supersedes_prescription_id": str(original.id)}, after=summary.model_dump(mode="json"),
            )
            return summary

    async def search_prescriptions(
        self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID | None, patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None, actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int,
    ) -> PrescriptionListResponse:
        effective_doctor_id = _own_scoped_doctor_filter(actor_role, actor_user_id, doctor_id)
        async with tenant_session(tenant_id) as session:
            rows, total = await PrescriptionRepository(session).search(
                tenant_id=tenant_id, encounter_id=encounter_id, patient_id=patient_id, doctor_id=effective_doctor_id, limit=limit, offset=offset
            )
            return PrescriptionListResponse(items=[PrescriptionSummary.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)

    async def get_prescription(self, *, tenant_id: uuid.UUID, prescription_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> PrescriptionSummary:
        async with tenant_session(tenant_id) as session:
            prescription = await PrescriptionRepository(session).get_by_id(prescription_id)
            if prescription is None or (actor_role == "DOCTOR" and prescription.doctor_id != actor_user_id):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
            return PrescriptionSummary.model_validate(prescription)

    async def get_print_view(
        self, *, tenant_id: uuid.UUID, prescription_id: uuid.UUID, mode: LetterheadPrintMode, actor_role: str, actor_user_id: uuid.UUID
    ) -> PrescriptionPrintView:
        summary = await self.get_prescription(tenant_id=tenant_id, prescription_id=prescription_id, actor_role=actor_role, actor_user_id=actor_user_id)
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(summary.encounter_id)
            assert encounter is not None
            branch_id = encounter.branch_id
        letterhead = await LetterheadService().resolve(tenant_id=tenant_id, mode=mode, branch_id=branch_id)
        return PrescriptionPrintView(prescription=summary, letterhead=letterhead)
