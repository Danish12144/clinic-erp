"""A direct product-owner deviation, not a matrix-seed gap fix — unlike
the earlier `role_permissions` gaps this file's own migrations chain has
fixed (0004/0010/0011/.../0029), the PRD §3 matrix's "Vitals recording"
row genuinely marks Receptionist "-" (migration 0012's own docstring
confirms this was seeded correctly: "Owner/Doctor/Nurse on, Receptionist
off"). The product owner explicitly asked for Receptionist to also be
able to view the OPD queue and record vitals alongside Nurse (front-desk
triage coverage when no nurse is on duty), so this grants `vitals.record`
to RECEPTIONIST outright rather than routing it through the existing
per-tenant `permission_overrides` mechanism migration 0012 already flagged
as the "proper" way to make this specific permission configurable —
Owner can still layer a *revoking* override on top for a clinic that
wants it back off, the mechanism is unaffected either way.

This is also what unlocks `/opd` in the frontend for Receptionist: the
route/nav guard there already checks `['consultation.manage',
'vitals.record']` (added when Nurse got the same frontend entry point,
commit c9a8255) — Receptionist reaches the same queue-list-only workspace
a Nurse does (consultation.manage stays Doctor/Owner-only), not the full
consultation pad.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-11

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('RECEPTIONIST', 'vitals.record')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'RECEPTIONIST')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'vitals.record')
        """
    )
