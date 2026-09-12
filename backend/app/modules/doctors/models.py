"""Doctor Management module: the DoctorProfile extension of a staff User,
and branch scoping for staff. See PRD-ARCHITECTURE.md §4 (module list item
7), §6 (entities), migration 0005.

`UserBranchAssignment` is deliberately generic to any role, not
doctor-specific — Staff Management reuses it rather than duplicating it.
The invite/accept-credentials mechanism (`StaffInvite`) originated in this
module's migration 0005 but its model/repository/endpoint were relocated
to the Auth module by migration 0006 (Staff Management) — see
app/modules/auth/models.py::StaffInvite for why.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint, DateTime, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    specialization: Mapped[str | None] = mapped_column(String, nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String, nullable=True)
    consultation_fee: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    working_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    # Phase 1 (migration 0033) — how far apart the staff Appointments
    # page's slot grid renders bookable times for this doctor. Purely a
    # scheduling-display concern, distinct from a specific appointment's
    # own `duration_minutes` (which a caller can still set to anything
    # 5-240 regardless of this default). Matches the frontend's previous
    # hardcoded 15-minute constant, so this column changes nothing for a
    # doctor nobody has explicitly reconfigured.
    slot_duration_minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("15"))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserBranchAssignment(Base):
    __tablename__ = "user_branch_assignments"
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
