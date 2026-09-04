"""CRM & Follow-ups — PRD-ARCHITECTURE.md §4 (module list items 29/30),
§5.6, §20, migration 0019. See that migration's docstring for the
deliberate scope narrowing (`follow_ups` is patient-only here, no `leads`)
and the `follow_up_status` deviation (`OVERDUE`, lazily computed — see
`app/modules/crm/service.py`).
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class FollowUpStatus(str, PyEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    OVERDUE = "OVERDUE"


follow_up_status_enum = SAEnum(FollowUpStatus, name="follow_up_status", create_type=False, values_callable=lambda enum: [m.value for m in enum])


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
    regardless of trigger. This module (Follow-ups) is the first, and so
    far only, writer — `status` never moves past `QUEUED` since there is
    no real SMS/WhatsApp provider wired in yet (task 3's "stubbed")."""

    __tablename__ = "communication_logs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    channel: Mapped[CommChannel] = mapped_column(comm_channel_enum, nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[CommStatus] = mapped_column(comm_status_enum, nullable=False, server_default=text("'QUEUED'::comm_status"))
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[FollowUpStatus] = mapped_column(follow_up_status_enum, nullable=False, server_default=text("'PENDING'::follow_up_status"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_log_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("communication_logs.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    reminder: Mapped["CommunicationLog | None"] = relationship()
