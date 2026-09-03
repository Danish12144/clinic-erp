"""Doctor Consultation, Clinical Notes & E-Prescription —
PRD-ARCHITECTURE.md §4 (module list items 17/18/19), §5.1, §6, migration
0013. See that migration's docstring for the deliberate schema deviations
(`prescription_items.medicine_id` has no FK yet, `route` was added) and the
permission-matrix deviation (Owner also writes, Nurse also reads — by
direct product-owner instruction, not the PRD §3 matrix's own default).

`Consultation` drives `Encounter.status` OPEN -> IN_CONSULTATION ->
COMPLETED (owned by this module, as flagged in Check-in's migration 0011).
`Prescription` is immutable-with-supersession (PRD §5.4/§5.7) — same
`prevent_update_delete()` mechanism `Vitals` uses; there is no update/
delete method for it anywhere in this module's repository, matching that
pattern. `PrescriptionItem` is NOT append-only — its `dispensed_quantity`
will be mutated by the future Pharmacy module.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Consultation(Base):
    __tablename__ = "consultations"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnosis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    icd10_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Prescription(Base):
    """Append-only: no `update`/`delete` anywhere in this module's
    repository — a correction is `POST /api/v1/prescriptions/{id}/supersede`,
    a new row referencing this one via `supersedes_prescription_id`."""

    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    supersedes_prescription_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("prescriptions.id"), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["PrescriptionItem"]] = relationship(order_by="PrescriptionItem.created_at")


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    prescription_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False)
    # No FK yet — see this module's migration (0013) docstring: `medicines`
    # doesn't exist until the Pharmacy module. Always NULL until then; the
    # API only accepts `medicine_name_freetext`.
    medicine_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    medicine_name_freetext: Mapped[str | None] = mapped_column(Text, nullable=True)
    dosage: Mapped[str | None] = mapped_column(Text, nullable=True)
    frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    prescribed_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dispensed_quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
