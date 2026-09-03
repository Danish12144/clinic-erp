"""Walk-in registration, check-in, and queue/token issuance — see
PRD-ARCHITECTURE.md §4 (module list items 12/13/14), §5.1 (steps 3/5/6),
§6 (entities), migration 0011.

`Encounter` is the hub entity for one clinic visit (PRD §7): vitals,
consultation, prescriptions, lab orders, and invoices will all key off it
in later modules, not off `Appointment` directly, because a walk-in may
have no appointment. This module only ever creates an `Encounter` as OPEN
(from a walk-in or from checking in an already-SCHEDULED appointment) or
lets front desk transition one to CANCELLED to correct a mistaken
check-in — transitioning into IN_CONSULTATION/COMPLETED belongs to the
not-yet-built Consultation module.

`QueueToken` is issued 1:1 with an `Encounter` at check-in time (unique
index on `encounter_id`) — a branch-wide daily sequence, never a
per-doctor one in the DB (a clinic wanting per-doctor numbering groups this
same branch-wide number at the display layer, per the master schema's own
note).
"""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class EncounterStatus(str, PyEnum):
    OPEN = "OPEN"
    IN_CONSULTATION = "IN_CONSULTATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


encounter_status_enum = SAEnum(
    EncounterStatus, name="encounter_status", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class QueueTokenStatus(str, PyEnum):
    WAITING = "WAITING"
    CALLED = "CALLED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    NO_SHOW = "NO_SHOW"
    SKIPPED = "SKIPPED"


queue_token_status_enum = SAEnum(
    QueueTokenStatus, name="queue_token_status", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    status: Mapped[EncounterStatus] = mapped_column(
        encounter_status_enum, nullable=False, server_default=text("'OPEN'::encounter_status")
    )
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QueueToken(Base):
    __tablename__ = "queue_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    token_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    token_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[QueueTokenStatus] = mapped_column(
        queue_token_status_enum, nullable=False, server_default=text("'WAITING'::queue_token_status")
    )
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
