"""Prescription PDF (view/download) surfaced a permission-matrix gap of
the exact same shape found repeatedly this session (migrations 0004,
0010, 0011, 0016, 0017, 0018): the PRD §3 matrix gives Patient "O (read)"
for "E-prescription," but migration 0013's seed only ever granted
`prescription.view` to Owner/Doctor/Nurse — Patient was never included.
Unnoticed until building real PDF view/download for patients (this
session's task) required Patient to actually be able to call
`GET /api/v1/prescriptions/{id}` at all.

`PrescriptionService.get_prescription`'s row-scoping is extended in the
same pass (a pure code change, not a migration) to check Patient-self
ownership via the prescription's `encounter.patient_id` — granting the
permission alone would otherwise let any Patient read any prescription by
id, since the existing scoping code only ever checked `actor_role ==
"DOCTOR"`.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('PATIENT', 'prescription.view')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'PATIENT')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'prescription.view')
        """
    )
