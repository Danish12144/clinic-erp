"""Patient EMR Timeline & Medical Documents business logic —
PRD-ARCHITECTURE.md §5.1 (step 8: "Doctor opens the Encounter, sees vitals
history, prior encounters (EMR)..."), §6, §15.

Row-scoping for `get_patient_emr_timeline` (the only read/write pair this
module gates with `patients.view_emr`): Owner is tenant-wide; Doctor is
scoped to patients they have *ever* consulted (not just their own
encounters within a mixed-doctor visit history — "own patients," matching
the PRD §2 role description "Own patients / assigned encounters," not
"own encounters only"); Patient is scoped to their own linked record. A
mismatch on any of these is a 404 (existence-hiding), same pattern
`AppointmentService.get_appointment` established. Date filtering
(`date_from`/`date_to`) applies to the visits and vitals sections, which
both already support it in their own repositories; prescriptions and
documents are capped by `limit` only — see this module's repository for
why extending two already-shipped repositories' signatures wasn't worth it
for this pass.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.consultation.repository import PrescriptionRepository
from app.modules.consultation.schemas import PrescriptionSummary
from app.modules.emr.models import MedicalDocumentType
from app.modules.emr.repository import EmrRepository, MedicalDocumentRepository
from app.modules.emr.schemas import (
    EmrVisitEntry,
    MedicalDocumentCreateRequest,
    MedicalDocumentListResponse,
    MedicalDocumentSummary,
    PatientEmrTimeline,
)
from app.modules.patients.repository import PatientRepository
from app.modules.vitals.repository import VitalsRepository
from app.modules.vitals.schemas import VitalsSummary


async def _check_emr_access(session, *, patient_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> None:
    if actor_role == "OWNER":
        return
    if actor_role == "DOCTOR":
        if not await EmrRepository(session).doctor_has_treated_patient(patient_id=patient_id, doctor_user_id=actor_user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
        return
    if actor_role == "PATIENT":
        own_patient = await PatientRepository(session).get_by_user_id(actor_user_id)
        if own_patient is None or own_patient.id != patient_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
        return
    # Unreachable in practice — only OWNER/DOCTOR/PATIENT hold
    # patients.view_emr — but fail closed rather than open if that ever changes.
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this patient's EMR")


class EmrService:
    async def get_patient_emr_timeline(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID,
        date_from: datetime | None, date_to: datetime | None, limit: int,
    ) -> PatientEmrTimeline:
        async with tenant_session(tenant_id) as session:
            if await PatientRepository(session).get_by_id(patient_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            await _check_emr_access(session, patient_id=patient_id, actor_role=actor_role, actor_user_id=actor_user_id)

            visit_rows = await EmrRepository(session).visits(
                tenant_id=tenant_id, patient_id=patient_id, date_from=date_from, date_to=date_to, limit=limit
            )
            visits = [
                EmrVisitEntry(
                    encounter_id=encounter.id, branch_id=encounter.branch_id, encounter_status=encounter.status.value,
                    checked_in_at=encounter.checked_in_at, completed_at=encounter.completed_at,
                    consultation_id=consultation.id, doctor_id=consultation.doctor_id,
                    chief_complaint=consultation.chief_complaint, diagnosis_text=consultation.diagnosis_text,
                    icd10_code=consultation.icd10_code, clinical_notes=consultation.clinical_notes,
                    started_at=consultation.started_at, ended_at=consultation.ended_at,
                )
                for encounter, consultation in visit_rows
            ]

            prescription_rows, _ = await PrescriptionRepository(session).search(
                tenant_id=tenant_id, encounter_id=None, patient_id=patient_id, doctor_id=None, limit=limit, offset=0
            )
            prescriptions = [PrescriptionSummary.model_validate(p) for p in prescription_rows]

            vitals_rows, _ = await VitalsRepository(session).search(
                tenant_id=tenant_id, encounter_id=None, patient_id=patient_id, recorded_by=None,
                date_from=date_from, date_to=date_to, limit=limit, offset=0,
            )
            vitals = [VitalsSummary.model_validate(v) for v in vitals_rows]

            document_rows, _ = await MedicalDocumentRepository(session).search(
                tenant_id=tenant_id, patient_id=patient_id, encounter_id=None, limit=limit, offset=0
            )
            documents = [MedicalDocumentSummary.model_validate(d) for d in document_rows]

            return PatientEmrTimeline(patient_id=patient_id, visits=visits, prescriptions=prescriptions, vitals=vitals, documents=documents)


class MedicalDocumentService:
    async def upload_document(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, payload: MedicalDocumentCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> MedicalDocumentSummary:
        async with tenant_session(tenant_id) as session:
            if await PatientRepository(session).get_by_id(patient_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Patient '{patient_id}' does not exist")

            document = await MedicalDocumentRepository(session).create(
                tenant_id=tenant_id, patient_id=patient_id, encounter_id=payload.encounter_id,
                document_type=MedicalDocumentType(payload.document_type), title=payload.title, storage_key=payload.storage_key,
                mime_type=payload.mime_type, file_size_bytes=payload.file_size_bytes, notes=payload.notes, uploaded_by=actor_user_id,
            )
            summary = MedicalDocumentSummary.model_validate(document)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="medical_document.upload", entity_type="medical_document", entity_id=document.id,
                before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def search_documents(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID, limit: int, offset: int
    ) -> MedicalDocumentListResponse:
        async with tenant_session(tenant_id) as session:
            if await PatientRepository(session).get_by_id(patient_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            await _check_emr_access(session, patient_id=patient_id, actor_role=actor_role, actor_user_id=actor_user_id)

            rows, total = await MedicalDocumentRepository(session).search(
                tenant_id=tenant_id, patient_id=patient_id, encounter_id=None, limit=limit, offset=offset
            )
            return MedicalDocumentListResponse(items=[MedicalDocumentSummary.model_validate(d) for d in rows], total=total, limit=limit, offset=offset)

    async def get_document(self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, document_id: uuid.UUID, actor_role: str, actor_user_id: uuid.UUID) -> MedicalDocumentSummary:
        async with tenant_session(tenant_id) as session:
            await _check_emr_access(session, patient_id=patient_id, actor_role=actor_role, actor_user_id=actor_user_id)
            document = await MedicalDocumentRepository(session).get_by_id(document_id)
            if document is None or document.patient_id != patient_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
            return MedicalDocumentSummary.model_validate(document)
