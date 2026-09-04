import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.consultation.schemas import PrescriptionSummary
from app.modules.vitals.schemas import VitalsSummary


class MedicalDocumentCreateRequest(BaseModel):
    encounter_id: uuid.UUID | None = None
    document_type: str = Field(..., description="One of LAB_REPORT, SCAN, XRAY, OTHER")
    title: str = Field(..., min_length=1, max_length=300)
    storage_key: str = Field(..., min_length=1, max_length=2000, description="An S3-style object key or an external URL — a pointer only, no file bytes pass through this API")
    mime_type: str | None = Field(None, max_length=200)
    file_size_bytes: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=1000)


class MedicalDocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None
    document_type: str
    title: str
    storage_key: str
    mime_type: str | None
    file_size_bytes: int | None
    notes: str | None
    uploaded_by: uuid.UUID
    created_at: datetime


class MedicalDocumentListResponse(BaseModel):
    items: list[MedicalDocumentSummary]
    total: int
    limit: int
    offset: int


class EmrVisitEntry(BaseModel):
    """One row per Encounter that reached a Consultation — the "sequential
    visit history" plus its diagnosis, since this schema has no separate
    Diagnosis entity: `diagnosis_text`/`icd10_code` live directly on
    `Consultation`."""

    encounter_id: uuid.UUID
    branch_id: uuid.UUID
    encounter_status: str
    checked_in_at: datetime
    completed_at: datetime | None
    consultation_id: uuid.UUID
    doctor_id: uuid.UUID
    chief_complaint: str | None
    diagnosis_text: str | None
    icd10_code: str | None
    clinical_notes: str | None
    started_at: datetime | None
    ended_at: datetime | None


class PatientEmrTimeline(BaseModel):
    patient_id: uuid.UUID
    visits: list[EmrVisitEntry]
    prescriptions: list[PrescriptionSummary]
    vitals: list[VitalsSummary]
    documents: list[MedicalDocumentSummary]
