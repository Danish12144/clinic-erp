"""Vitals — PRD-ARCHITECTURE.md §4 (module list item 15), §5.1, §6,
migration 0012.

Append-only by design (PRD §5.3): "never overwrite the previous reading,
preserve the history" — enforced both by a `BEFORE UPDATE OR DELETE`
trigger (`prevent_update_delete()`) and by `app_user` having no UPDATE/
DELETE grant on this table, so there is no `update`/`delete` method
anywhere in this module's repository — only `create` and reads. `bmi` is a
DB-generated column (`GENERATED ALWAYS AS ... STORED`), computed from
`weight_kg`/`height_cm` whenever both are present; SQLAlchemy maps it
read-only via `Computed(..., persisted=True)` so the ORM never tries to
write it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Computed

from app.core.db import Base


class Vitals(Base):
    __tablename__ = "vitals"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    recorded_by_role: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    systolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature_celsius: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    spo2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    bmi: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        Computed(
            "CASE WHEN weight_kg IS NOT NULL AND height_cm IS NOT NULL AND height_cm > 0 "
            "THEN ROUND((weight_kg / ((height_cm / 100.0) ^ 2))::numeric, 2) ELSE NULL END",
            persisted=True,
        ),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
