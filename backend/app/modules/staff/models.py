"""Staff Management module: the StaffProfile extension of a non-doctor
staff User (Receptionist, Nurse, Lab Staff, Pharmacy Staff, Other Staff).
See PRD-ARCHITECTURE.md §4 (module list item 8), §6 (entities),
migration 0006.

Branch scoping (`UserBranchAssignment`, `app.modules.doctors.models`) and
the invite/accept mechanism (`StaffInvite`, `app.modules.auth.models`) are
reused as-is from where Doctor Management (and, for the invite, a
relocation into Auth) already built them — both were designed generic to
any staff role for exactly this reuse.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    employee_code: Mapped[str | None] = mapped_column(String, nullable=True)
    designation: Mapped[str | None] = mapped_column(String, nullable=True)
    joining_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
