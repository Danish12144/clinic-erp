"""Tenancy module: the tenant root (Clinic), its physical locations
(Branch), and a generic per-tenant settings bag (TenantSetting). See
PRD-ARCHITECTURE.md §4 (tenancy strategy), §22 (multi-branch), §10 module
list items 4/5/6.

`Clinic` was originally added under the Auth module (it needed the tenant
root to resolve a clinic by slug and scope users) — it lives here now that
the Tenancy module owns it; Auth still imports it from this module.

Deliberately NOT in this module: `Subscription`/billing (PRD §30 open
question — pricing model undecided), Clinic *creation*/onboarding (a
Platform Admin concern — no Platform Admin auth exists yet). This module
only manages settings/branches for a clinic that already exists.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ClinicStatus(str, PyEnum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"


clinic_status_enum = SAEnum(
    ClinicStatus, name="clinic_status", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'Asia/Kolkata'"))
    locale: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'en-IN'"))
    gst_number: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[ClinicStatus] = mapped_column(clinic_status_enum, nullable=False, server_default=text("'TRIAL'::clinic_status"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Branch(Base):
    """A clinic's physical location. Most day-to-day operational entities
    (appointments, encounters, invoices, inventory — built in later
    modules) are branch-scoped; `Patient` is tenant-scoped, not
    branch-scoped (PRD §22 — the recommended, not-yet-explicitly-confirmed
    "one tenant, many branches" model)."""

    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_branch_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    working_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantSetting(Base):
    """Generic per-tenant settings bag (branding, defaults, feature
    flags — PRD §4). Deliberately unstructured (a JSONB value under an
    arbitrary key) rather than a fixed set of columns, since the set of
    things a clinic might want to configure is expected to grow across
    later modules without needing a schema migration each time."""

    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_tenant_setting_key"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
