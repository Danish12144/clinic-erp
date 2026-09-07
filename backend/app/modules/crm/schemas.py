import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.models import CommChannel


class FollowUpCreateRequest(BaseModel):
    patient_id: uuid.UUID
    doctor_id: uuid.UUID | None = None
    encounter_id: uuid.UUID | None = None
    due_at: datetime
    reason: str | None = Field(None, max_length=1000, description='e.g. "post-treatment check", "suture removal", "chronic review"')
    channel: CommChannel = Field(CommChannel.WHATSAPP, description="Channel for the stubbed reminder outbox entry (task 3) — no real message is sent")


class FollowUpStatusUpdateRequest(BaseModel):
    status: str = Field(..., description="One of SENT, CONFIRMED, CANCELLED, PENDING (re-queue from SKIPPED-like states)")


class CommunicationLogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    channel: str
    status: str
    sent_at: datetime | None
    created_at: datetime


class FollowUpSummary(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID | None
    encounter_id: uuid.UUID | None
    due_at: datetime
    status: str
    reason: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    reminder: CommunicationLogSummary | None


class FollowUpListResponse(BaseModel):
    items: list[FollowUpSummary]
    total: int
    limit: int
    offset: int
