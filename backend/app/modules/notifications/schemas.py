import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.notifications.models import CommChannel, CommStatus

_MAX_VARIABLES = 30
_MAX_VARIABLE_LENGTH = 100


class NotificationTemplateCreateRequest(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=100, description='e.g. "APPOINTMENT_BOOKED", "BILL_RECEIPT" — an open, non-exhaustive set of trigger keys')
    channel: CommChannel
    body_text: str = Field(..., min_length=1, max_length=2000)
    variables: list[str] = Field(default_factory=list, description='Placeholder names referenced in body_text as "{{name}}", e.g. ["patient_name", "appointment_time"]')
    is_active: bool = True

    @model_validator(mode="after")
    def validate_variables(self) -> "NotificationTemplateCreateRequest":
        if len(self.variables) > _MAX_VARIABLES:
            raise ValueError(f"variables cannot have more than {_MAX_VARIABLES} entries")
        for name in self.variables:
            if not name or len(name) > _MAX_VARIABLE_LENGTH:
                raise ValueError(f"each variable name must be 1-{_MAX_VARIABLE_LENGTH} characters")
        return self


class NotificationTemplateUpdateRequest(BaseModel):
    """Text/variables/active-state only, per this task's own wording
    ("update template text or toggle active state") — `template_key`/
    `channel` are the template's identity and stay immutable after
    creation, same "identity fields aren't patchable" convention as
    `PharmacySale.payment_mode` or `MedicineBatch.batch_number`."""

    body_text: str | None = Field(None, min_length=1, max_length=2000)
    variables: list[str] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_variables(self) -> "NotificationTemplateUpdateRequest":
        if self.variables is not None:
            if len(self.variables) > _MAX_VARIABLES:
                raise ValueError(f"variables cannot have more than {_MAX_VARIABLES} entries")
            for name in self.variables:
                if not name or len(name) > _MAX_VARIABLE_LENGTH:
                    raise ValueError(f"each variable name must be 1-{_MAX_VARIABLE_LENGTH} characters")
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class NotificationTemplateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    template_key: str
    channel: CommChannel
    body_text: str
    variables: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationTemplateListResponse(BaseModel):
    items: list[NotificationTemplateSummary]
    total: int
    limit: int
    offset: int


# ---- Preview --------------------------------------------------------------------


class SendPreviewRequest(BaseModel):
    template_id: uuid.UUID
    sample_data: dict[str, str] = Field(default_factory=dict, description="Mock values for the template's placeholders, e.g. {\"patient_name\": \"Jane Doe\"}")


class SendPreviewResponse(BaseModel):
    template_id: uuid.UUID
    rendered_body: str


# ---- Logs -----------------------------------------------------------------------


class CommunicationLogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    patient_id: uuid.UUID | None
    channel: CommChannel
    template_id: uuid.UUID | None
    rendered_body: str | None
    status: CommStatus
    sent_at: datetime | None
    created_at: datetime


class CommunicationLogListResponse(BaseModel):
    items: list[CommunicationLogSummary]
    total: int
    limit: int
    offset: int
