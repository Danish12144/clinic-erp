import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.appointments.schemas import AppointmentSummary
from app.modules.checkin.models import QueueTokenStatus


class WalkInRequest(BaseModel):
    """Registers a walk-in visit directly into the queue — PRD §5.1 step 3.
    The patient must already be registered (via Patient Management); this
    endpoint does not create a `Patient`. `doctor_id` is optional — a
    walk-in may arrive before front desk has assigned a doctor."""

    patient_id: uuid.UUID
    branch_id: uuid.UUID
    doctor_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=1000)


class EncounterSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    appointment_id: uuid.UUID | None
    patient_id: uuid.UUID
    status: str
    checked_in_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EncounterListResponse(BaseModel):
    items: list[EncounterSummary]
    total: int
    limit: int
    offset: int


class QueueTokenSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    encounter_id: uuid.UUID
    doctor_id: uuid.UUID | None
    token_date: date
    token_number: int
    status: str
    called_at: datetime | None
    created_at: datetime
    updated_at: datetime


class QueueListResponse(BaseModel):
    items: list[QueueTokenSummary]
    total: int
    limit: int
    offset: int


class CheckInResult(BaseModel):
    """Returned by both walk-in registration and check-in-an-appointment —
    a single front-desk action always produces an Encounter plus the
    QueueToken issued for it in the same transaction. `appointment` is the
    WALK_IN appointment created retroactively for a walk-in, or the
    existing appointment that was just checked in."""

    appointment: AppointmentSummary
    encounter: EncounterSummary
    queue_token: QueueTokenSummary


class EncounterCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class QueueStatusUpdateRequest(BaseModel):
    status: QueueTokenStatus
