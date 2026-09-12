"""Appointments module: booking only (online + receptionist) — see
PRD-ARCHITECTURE.md §4 (module list items 10/11), §5.1 (steps 1-2), §6
(entities), migration 0010.

Deliberately NOT in this module (out of scope by explicit product
decision, separate future modules): walk-in registration (`source =
WALK_IN` is schema-ready but nothing creates one yet), check-in
(`status = CHECKED_IN` and the `Encounter` it should create), queue/token
management, and marking `NO_SHOW` (a day-of front-desk action that
belongs with check-in, not booking). This module only creates, reschedules,
and cancels a `SCHEDULED` appointment.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppointmentSource(str, PyEnum):
    ONLINE = "ONLINE"
    RECEPTIONIST = "RECEPTIONIST"
    WALK_IN = "WALK_IN"


appointment_source_enum = SAEnum(
    AppointmentSource, name="appointment_source", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class AppointmentStatus(str, PyEnum):
    SCHEDULED = "SCHEDULED"
    CHECKED_IN = "CHECKED_IN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


appointment_status_enum = SAEnum(
    AppointmentStatus, name="appointment_status", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class AppointmentPaymentStatus(str, PyEnum):
    """Phase 2 (Master Handoff item 5) — orthogonal to `AppointmentStatus`
    above, which is the clinical day-of workflow (arrival/consultation/
    completion) and untouched by this. This tracks the separate "did an
    online prepayment on this booking succeed" lifecycle (migration 0034):
    NOT_REQUIRED (the default — every staff/walk-in booking, and any
    public booking that didn't opt into prepayment) never changes.
    PENDING -> CONFIRMED/FAILED is set only by the payment gateway webhook
    (`PaymentGatewayWebhookService`); FAILED -> PENDING again is the
    "retry" path (a fresh gateway order); CONFIRMED -> REFUNDED happens
    only when the appointment is cancelled after a confirmed prepayment.
    Never set directly by request/reschedule/cancel logic otherwise — the
    same "always derived, only at specific transition points" discipline
    `Invoice.status` already follows."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


appointment_payment_status_enum = SAEnum(
    AppointmentPaymentStatus, name="appointment_payment_status", create_type=False,
    values_callable=lambda enum: [m.value for m in enum],
)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source: Mapped[AppointmentSource] = mapped_column(appointment_source_enum, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("15"))
    status: Mapped[AppointmentStatus] = mapped_column(
        appointment_status_enum, nullable=False, server_default=text("'SCHEDULED'::appointment_status")
    )
    payment_status: Mapped[AppointmentPaymentStatus] = mapped_column(
        appointment_payment_status_enum, nullable=False, server_default=text("'NOT_REQUIRED'::appointment_payment_status")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
