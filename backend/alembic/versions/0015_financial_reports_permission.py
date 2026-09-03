"""Financial Reports & Analytics Aggregation — PRD-ARCHITECTURE.md §4
(module list item, "Owner dashboard, analytics, reports"), §16 (analytics/
reporting). Pure read/aggregation over existing `invoices`/
`invoice_line_items`/`payments`/`consultations` data — no new tables.

Permission-matrix deviation, by direct instruction (not a seed-vs-matrix
gap fix, same category as migration `0013`'s Consultation/Prescription
RBAC): the PRD §3 matrix marks "Owner dashboard, analytics, reports" as
Owner "F" and **every other role "–"**, including Doctor. The product
owner explicitly asked for "Doctor's dashboard... strictly row-scoped to
their own revenue/consultations" — i.e. Doctor needs *some* access to this
capability, just scoped, not the "–" the matrix currently gives them.

Adds `dashboard.view_own` (Doctor only, row-scoped to their own
`doctor_id` at the service layer — the same `.manage`/`.view_own` split
already established for Billing's `billing.manage`/`billing.view_own`)
rather than granting Doctor the existing `dashboard.view` (which stays
Owner-only, unscoped, exactly as the matrix and migration `0001` already
have it) — so a future permission audit can tell at a glance that Doctor's
grant is a distinct, narrower capability, not an accidental widening of
the Owner one.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('dashboard.view_own', 'analytics', 'View own revenue/consultation analytics — Doctor only, row-scoped')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('DOCTOR', 'dashboard.view_own')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'dashboard.view_own')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'dashboard.view_own'")
