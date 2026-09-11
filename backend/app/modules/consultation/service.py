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
from app.modules.auth.repository import UserRepository
from app.modules.billing.schemas import AutoGenerateInvoiceRequest
from app.modules.billing.service import BillingService
from app.modules.checkin.models import EncounterStatus, QueueTokenStatus
from app.modules.checkin.repository import EncounterRepository, QueueTokenRepository
from app.modules.consultation.models import Prescription
from app.modules.consultation.pdf import PrescriptionPdfItem, render_prescription_pdf
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
from app.modules.files.repository import DocumentRepository
from app.modules.files.service import store_generated_document
from app.modules.letterhead.schemas import LetterheadPrintMode
from app.modules.letterhead.service import LetterheadService
from app.modules.patients.repository import PatientRepository
from app.modules.pharmacy.repository import MedicineRepository

_PRESCRIPTION_PDF_OWNER_TYPE = "PRESCRIPTION_PDF"


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

            # Bypasses checkin/service.py's own _ALLOWED_QUEUE_TRANSITIONS
            # validation deliberately -- that map exists to guard the
            # receptionist-facing PATCH /queue/{id} endpoint (a human
            # picking an arbitrary next state), not a system-driven
            # transition this service already knows is correct because it
            # just started the consultation itself. Same "direct repository
            # call, no revalidation" precedent CheckInService.cancel_encounter
            # already uses for its own SKIPPED transition. A token that was
            # never CALLED (this app has no working front-desk "call next"
            # UI yet -- see CLAUDE.md) still needs to reach IN_PROGRESS
            # somehow, so this jumps straight there from whatever it was.
            token = await QueueTokenRepository(session).get_by_encounter_id(encounter.id)
            if token is not None and token.status not in (QueueTokenStatus.DONE, QueueTokenStatus.NO_SHOW, QueueTokenStatus.IN_PROGRESS):
                before_token_status = token.status.value
                await QueueTokenRepository(session).update_status(token.id, status=QueueTokenStatus.IN_PROGRESS)
                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="queue_token.status_change", entity_type="queue_token", entity_id=token.id,
                    before={"status": before_token_status}, after={"status": QueueTokenStatus.IN_PROGRESS.value},
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

            # See start_consultation's own comment for why this bypasses
            # checkin/service.py's transition validation directly — same
            # reasoning, just the DONE end of the same state machine
            # (PRD-ARCHITECTURE.md §5.1 step 6: "WAITING -> CALLED ->
            # IN_PROGRESS -> DONE / NO_SHOW / SKIPPED").
            token = await QueueTokenRepository(session).get_by_encounter_id(encounter.id)
            if token is not None and token.status not in (QueueTokenStatus.DONE, QueueTokenStatus.NO_SHOW):
                before_token_status = token.status.value
                await QueueTokenRepository(session).update_status(token.id, status=QueueTokenStatus.DONE)
                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="queue_token.status_change", entity_type="queue_token", entity_id=token.id,
                    before={"status": before_token_status}, after={"status": QueueTokenStatus.DONE.value},
                )

        # Outside the transaction above, deliberately -- PRD-ARCHITECTURE.md
        # §5.1 step 11 ("Billing generated... can be partially generated as
        # the visit progresses... rather than only at the end") frames this
        # as best-effort, not a hard requirement the clinical action itself
        # should fail on. A doctor with no consultation_fee configured, or
        # an invoice a receptionist already raised mid-visit, are both
        # legitimate reasons auto_generate_invoice 422s/409s -- neither
        # should block the consultation from completing, so this is a
        # separate, independent transaction that's allowed to fail quietly.
        try:
            await BillingService().auto_generate_invoice(
                tenant_id=tenant_id, payload=AutoGenerateInvoiceRequest(encounter_id=encounter.id),
                actor_user_id=actor_user_id, actor_role=actor_role,
            )
        except HTTPException:
            pass
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


async def _generate_and_store_prescription_pdf(session, *, tenant_id: uuid.UUID, prescription: Prescription, actor_user_id: uuid.UUID):
    """Called once, right after `create_with_items`, from both
    `issue_prescription` and `supersede_prescription` — a correction is a
    new `Prescription` row (§5.7's supersession rule), so it gets its own
    fresh PDF, the original's untouched. Synchronous, inline in the same
    transaction as the prescription itself (no Celery/Redis exists in this
    backend to defer it to, and rendering a simple document is fast) —
    per direct instruction, "direct dispatch" over `BackgroundTasks` here,
    since deferring would mean the PDF isn't ready by the time the caller
    gets a response, and this module's own transaction-atomicity
    convention (audit commits with the change it describes) already
    assumes everything happens in one transaction."""
    encounter = await EncounterRepository(session).get_by_id(prescription.encounter_id)
    assert encounter is not None
    patient = await PatientRepository(session).get_by_id(encounter.patient_id)
    assert patient is not None
    doctor_user = await UserRepository(session).get_by_id(prescription.doctor_id)
    assert doctor_user is not None

    resolved_items = []
    for item in prescription.items:
        if item.medicine_name_freetext is not None:
            name = item.medicine_name_freetext
        else:
            medicine = await MedicineRepository(session).get_by_id(item.medicine_id)
            assert medicine is not None
            name = medicine.name
        resolved_items.append(PrescriptionPdfItem(
            medicine_name=name, dosage=item.dosage, frequency=item.frequency, duration=item.duration,
            route=item.route, prescribed_quantity=item.prescribed_quantity, instructions=item.instructions,
        ))

    letterhead = await LetterheadService().resolve(tenant_id=tenant_id, mode=LetterheadPrintMode.DIGITAL, branch_id=encounter.branch_id)
    patient_name = f"{patient.first_name} {patient.last_name}".strip() if patient.last_name else patient.first_name
    doctor_name = f"{doctor_user.first_name or ''} {doctor_user.last_name or ''}".strip() or "Doctor"

    pdf_bytes = render_prescription_pdf(
        patient_name=patient_name, doctor_name=doctor_name, issued_at=prescription.issued_at, items=resolved_items, letterhead=letterhead,
    )
    return await store_generated_document(
        session, tenant_id=tenant_id, owner_type=_PRESCRIPTION_PDF_OWNER_TYPE, owner_id=prescription.id,
        filename=f"prescription-{prescription.id}.pdf", content_type="application/pdf", content=pdf_bytes, uploaded_by=actor_user_id,
    )


async def _find_prescription_pdf(session, *, tenant_id: uuid.UUID, prescription_id: uuid.UUID) -> tuple[uuid.UUID | None, str | None]:
    documents, _ = await DocumentRepository(session).search(tenant_id=tenant_id, owner_type=_PRESCRIPTION_PDF_OWNER_TYPE, owner_id=prescription_id, limit=1, offset=0)
    if not documents:
        return None, None
    return documents[0].id, f"/api/v1/files/{documents[0].id}/content"


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
            document = await _generate_and_store_prescription_pdf(session, tenant_id=tenant_id, prescription=full, actor_user_id=actor_user_id)
            summary = PrescriptionSummary.model_validate(full)
            summary.pdf_document_id = document.id
            summary.pdf_download_url = f"/api/v1/files/{document.id}/content"
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
            document = await _generate_and_store_prescription_pdf(session, tenant_id=tenant_id, prescription=full, actor_user_id=actor_user_id)
            summary = PrescriptionSummary.model_validate(full)
            summary.pdf_document_id = document.id
            summary.pdf_download_url = f"/api/v1/files/{document.id}/content"
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
            # pdf_document_id/pdf_download_url are deliberately left null in
            # list results (an N+1 lookup per row isn't worth it for this
            # task's own "view/download a single prescription" ask) — use
            # GET /{id} to get the PDF link for a specific prescription.
            return PrescriptionListResponse(items=[PrescriptionSummary.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)

    async def get_prescription(self, *, tenant_id: uuid.UUID, prescription_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> PrescriptionSummary:
        async with tenant_session(tenant_id) as session:
            prescription = await PrescriptionRepository(session).get_by_id(prescription_id)
            if prescription is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
            if actor_role == "DOCTOR" and prescription.doctor_id != actor_user_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")
            if actor_role == "PATIENT":
                # Migration 0026 gap-fix companion: Patient now holds
                # prescription.view but the code never checked *which*
                # patient — added here, same existence-hiding pattern as
                # the Doctor check above.
                encounter = await EncounterRepository(session).get_by_id(prescription.encounter_id)
                own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
                if encounter is None or own_patient is None or encounter.patient_id != own_patient.id:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription not found")

            summary = PrescriptionSummary.model_validate(prescription)
            summary.pdf_document_id, summary.pdf_download_url = await _find_prescription_pdf(session, tenant_id=tenant_id, prescription_id=prescription_id)
            return summary

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
