"""Doctor directory read permission: `doctors.view_directory`, granted to
RECEPTIONIST and PATIENT. Not in the original PRD §3 matrix ("Doctor
profile management" is Owner F / Doctor O / everyone else –) — added by
explicit product decision ahead of Appointments (Phase 2), which needs a
way for a Receptionist or a Patient to see which doctors are bookable
without reopening the Owner-only management view or its PII-bearing
response shape. See app/modules/doctors/router.py's `GET /directory` and
DoctorRepository.search_directory (ACTIVE doctors only).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('doctors.view_directory', 'doctors', 'View the read-only doctor directory (name, specialization, fee, schedule) for booking')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('RECEPTIONIST','doctors.view_directory'),
          ('PATIENT','doctors.view_directory')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'doctors.view_directory')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'doctors.view_directory'")
