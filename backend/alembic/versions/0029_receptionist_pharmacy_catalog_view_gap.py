"""Building the OTC Sales / POS frontend surfaced a second matrix-shaped
gap in the same module as migration 0028, found the same way (building
the actual consumer screen, not a backend test): migration 0021 granted
Receptionist `pharmacy.sell_otc` (the write — checkout a sale) but never
`pharmacy.view_catalog` (the read every checkout screen needs first, to
search for what's actually being sold — `GET /api/v1/pharmacy/medicines`
is gated by `pharmacy.view_catalog` alone, not by either sales
permission). Owner/Pharmacy Staff already hold `pharmacy.view_catalog`
directly, so this was invisible until Receptionist — the other role
`pharmacy.sell_otc` exists for — tried to build a cart.

Granting the read permission doesn't widen what Receptionist can do
beyond what migration 0021 already intended: `pharmacy.view_catalog` is
read-only (browsing name/price/stock), and every catalog *write* route
(`pharmacy.manage_catalog`) and prescription dispensing
(`pharmacy.dispense`) stay exactly as gated as before — Receptionist
still cannot dispense a prescription or edit the catalog, only look it up
to ring up an OTC sale, which is the capability 0021 already granted the
write side of.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-10

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('RECEPTIONIST', 'pharmacy.view_catalog')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE code = 'RECEPTIONIST')
          AND permission_id = (SELECT id FROM permissions WHERE code = 'pharmacy.view_catalog')
        """
    )
