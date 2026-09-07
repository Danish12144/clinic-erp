"""Patient Management module: the Patient entity itself — demographics,
registration, and search. See PRD-ARCHITECTURE.md §6 (entities), §9
(module list item 9).

Deliberately NOT in this module (belong to later modules): encounters,
vitals, consultations, prescriptions — "EMR / patient medical records"
(PRD module list item 16) is a distinct module built on top of this one.
Patient portal account linking (`user_id`) is schema-ready but no flow to
set it exists yet — that's Patient Portal (Phase 6).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import ARRAY, CheckConstraint, Date, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (CheckConstraint("gender IN ('Male','Female','Other')", name="ck_patients_gender"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    mrn: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String, nullable=True)
    allergies: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    chronic_conditions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{}'"))
    emergency_contact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    # ABHA/ABDM preparedness (migration 0027) — deliberately lightweight,
    # not the master schema's fuller reserved `AbhaLink` table; see that
    # migration's own docstring. Writing a non-null value here is gated by
    # the `features.abdm_enabled` TenantSetting at the service layer, not
    # by anything at this model/DB level.
    abha_id: Mapped[str | None] = mapped_column(String, nullable=True)
    abha_address: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
