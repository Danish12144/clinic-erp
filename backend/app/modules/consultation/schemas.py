import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.letterhead.schemas import LetterheadResolved


class ConsultationStartRequest(BaseModel):
    encounter_id: uuid.UUID
    chief_complaint: str | None = Field(None, max_length=2000)


class ConsultationUpdateRequest(BaseModel):
    """Editable while the consultation is still open (`ended_at` is null).
    Once `complete`d, a consultation has no edit endpoint at all — it isn't
    DB-append-only like `Prescription` (PRD gives that guarantee only to
    vitals/prescriptions/audit_logs), but "no edits after the visit is
    closed" is enforced at the service layer instead."""

    chief_complaint: str | None = Field(None, max_length=2000)
    clinical_notes: str | None = Field(None, max_length=10000)
    diagnosis_text: str | None = Field(None, max_length=2000)
    icd10_code: str | None = Field(None, max_length=20)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ConsultationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ConsultationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    doctor_id: uuid.UUID
    chief_complaint: str | None
    clinical_notes: str | None
    diagnosis_text: str | None
    icd10_code: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConsultationListResponse(BaseModel):
    items: list[ConsultationSummary]
    total: int
    limit: int
    offset: int


# ---- Prescriptions ----------------------------------------------------------


class PrescriptionItemCreateRequest(BaseModel):
    """`medicine_id` (a catalog reference) is optional — pass it to link
    the item to the Pharmacy module's catalog (validated against the
    tenant's `medicines` table by `PrescriptionService`, added once that
    module existed — see migration 0017) so it can later be dispensed
    against inventory; omit it for a free-text item not in the catalog.
    At least one of `medicine_id`/`medicine_name_freetext` is required,
    matching the DB's own `CHECK` constraint."""

    medicine_id: uuid.UUID | None = None
    medicine_name_freetext: str | None = Field(None, min_length=1, max_length=300)
    dosage: str | None = Field(None, max_length=200)
    frequency: str | None = Field(None, max_length=200)
    duration: str | None = Field(None, max_length=200)
    route: str | None = Field(None, max_length=100)
    prescribed_quantity: int = Field(..., ge=1, le=10000)
    instructions: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def medicine_id_or_freetext(self) -> "PrescriptionItemCreateRequest":
        if self.medicine_id is None and not self.medicine_name_freetext:
            raise ValueError("either medicine_id or medicine_name_freetext must be provided")
        return self


class PrescriptionCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    items: list[PrescriptionItemCreateRequest] = Field(..., min_length=1, max_length=50)


class PrescriptionItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prescription_id: uuid.UUID
    medicine_id: uuid.UUID | None
    medicine_name_freetext: str | None
    dosage: str | None
    frequency: str | None
    duration: str | None
    route: str | None
    prescribed_quantity: int
    dispensed_quantity: int
    instructions: str | None


class PrescriptionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    encounter_id: uuid.UUID
    doctor_id: uuid.UUID
    supersedes_prescription_id: uuid.UUID | None
    issued_at: datetime
    created_at: datetime
    items: list[PrescriptionItemSummary]
    pdf_document_id: uuid.UUID | None = None
    pdf_download_url: str | None = Field(None, description="GET this URL (via /api/v1/files/{id}/content) to download the rendered PDF")


class PrescriptionListResponse(BaseModel):
    items: list[PrescriptionSummary]
    total: int
    limit: int
    offset: int


class PrescriptionPrintView(BaseModel):
    """The one concrete consumer of Clinic Letterhead Configuration wired
    up so far — the toggle a frontend needs to render/print a prescription
    either DIGITAL or PHYSICAL. No PDF is generated here; see
    app/modules/letterhead/service.py's module docstring for why."""

    prescription: PrescriptionSummary
    letterhead: LetterheadResolved
