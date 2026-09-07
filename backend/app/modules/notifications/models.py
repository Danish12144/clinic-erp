"""Notification Templates & Outbox Integration — PRD-ARCHITECTURE.md §4
(module list item 31), §20, §6, migration 0024. See that migration's
docstring for the deliberate deviations from the master schema's
`notification_templates` sketch (reusing `comm_channel`, free-text
`template_key`, JSONB `variables`) and for the `communication_logs`
gap-fills (`rendered_body`, the `template_id` FK finally added).

`CommChannel`/`CommStatus`/`CommunicationLog` moved here from
`app.modules.crm.models` (migration 0019's original home) — a pure code
move, no table/column rename — because Notifications is now the true
owner of the outbox concept: every business-trigger dispatch (Appointments,
Billing, Lab, CRM) goes through `app.modules.notifications.service.
dispatch_notification`, not just Follow-ups' own stub-insert anymore. Same
"relocate once it needs a second caller" precedent `StaffInvite` set when
it moved from `doctors` to `auth`.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, ForeignKey, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CommChannel(str, PyEnum):
    WHATSAPP = "WHATSAPP"
    SMS = "SMS"
    EMAIL = "EMAIL"
    PUSH = "PUSH"


comm_channel_enum = SAEnum(CommChannel, name="comm_channel", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class CommStatus(str, PyEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


comm_status_enum = SAEnum(CommStatus, name="comm_status", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class CommunicationLog(Base):
    """PRD §20: every outbound patient-facing message lands here,
    regardless of trigger. `status` never moves past `QUEUED` since there
    is no real SMS/WhatsApp/Email provider wired in anywhere in this
    backend (task 3's "stubbed") — `dispatch_notification` is the one
    writer for every business trigger; Follow-ups (CRM) now calls it too
    instead of inserting a bare stub row itself."""

    __tablename__ = "communication_logs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    channel: Mapped[CommChannel] = mapped_column(comm_channel_enum, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("notification_templates.id"), nullable=True)
    rendered_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CommStatus] = mapped_column(comm_status_enum, nullable=False, server_default=text("'QUEUED'::comm_status"))
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    template_key: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[CommChannel] = mapped_column(comm_channel_enum, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
