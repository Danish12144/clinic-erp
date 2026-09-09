"""Building the Pharmacy Dispense frontend surfaced a permission-matrix
gap of the exact same shape found repeatedly this project (migrations
0004, 0010, 0011, 0016, 0017, 0018, 0026): the PRD §3 matrix gives
Pharmacy Staff "F" (full) on "Pharmacy dispensing / POS," but dispensing
is only ever performed against a specific `prescription_item_id`
(`POST /api/v1/pharmacy/dispense`, see backend/app/modules/pharmacy/
schemas.py::DispenseRequest) — there was no way for Pharmacy Staff to
even find that id, since migration 0013's `prescription.view` seed only
ever granted Owner/Doctor/Nurse (and migration 0026 added Patient).
Pharmacy Staff was never included, making the dispense workflow
impossible to use from the UI: no prescription list, no pending items.

`PrescriptionService.search_prescriptions`/`get_prescription` only
special-case the `DOCTOR` (own-only) and `PATIENT` (self-only) roles —
any other role holding `prescription.view` (Owner, Nurse, and now
Pharmacy Staff) already gets unscoped tenant-wide read access, the same
as Owner/Nurse today. No service-layer code change needed, unlike
migration 0026's companion Patient-self-scoping fix — Pharmacy Staff
legitimately needs to see every patient's pending prescriptions to do
their job at the counter, the same reasoning that already applies to
Owner/Nurse.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-10

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('PHARMACY_STAFF', 'prescription.view')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'PHARMACY_STAFF')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'prescription.view')
        """
    )
