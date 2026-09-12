"""Phase 1 (Master Handoff §5 "HIGH — Accounts", §9 role-by-role target
"Accountant") — closes a gap the pre-Phase-1 audit found and the Master
Prompt names explicitly: this system's fixed 8-role model (migration
0001, `app/modules/auth/models.py::Role`'s own "system-defined roles
only" docstring) has no role called Accountant, and `OTHER_STAFF` — the
role a finance person is provisioned under today (see
scripts/seed_demo_accounts.py's own ACCOUNTANT -> OTHER_STAFF mapping
comment) — has no default permission touching billing, payments,
expenses, or reports at all. An accounts person logging in today sees
nothing to reconcile.

Deliberately NOT a ninth role. Adding one would mean touching every
`Literal`/enum-shaped role_code reference across both stacks (Python
Literals, the frontend's `ROLE_CODES` union, staff-creation dropdowns,
this project's own STAFF_ROLE_CODES constant) for a single permission
bundle — exactly the "do not rebuild the architecture" the Master Prompt
rules out, for zero capability this project's own `permission_overrides`
mechanism doesn't already provide. Two new permission codes only, granted
to NO role by default:

  - `billing.view`   — tenant-wide, READ-ONLY invoices *and* their nested
    payments (mirrors `billing.manage`'s unscoped reach, not
    `billing.view_own`'s row-scoping — see BillingService.search_invoices/
    get_invoice, whose row-scoping is keyed on `actor_role in
    ("DOCTOR","PATIENT")`, so a caller reaching a route through
    `billing.view` alone is naturally unscoped without any service-layer
    change). Also widens the standalone `GET /billing/payments` list,
    which was `payments.record`-only before this — a real gap, since that
    endpoint is the more useful one for reconciling money received across
    every invoice at once, not per-invoice.
  - `expenses.view`  — tenant-wide, READ-ONLY expenses, split out from the
    existing `_READ_WRITE_PERMS` tuple that used to gate both the create
    (POST) and read (GET) routes identically — a view-only grant must not
    also unlock creating expenses.

Reports/dashboard needs no new code: `GET /reports/financial` and
`GET /billing/summary` already gate on `require_any_permission("dashboard.
view", "dashboard.view_own")` (migration 0015), and `dashboard.view`'s own
row-scoping is likewise keyed only on `actor_role == "DOCTOR"` — granting
it to a non-Doctor caller already produces tenant-wide, unscoped reports.

Applying the bundle to a real person is what `permission_overrides`
(migration 0001, its write path added later) is *for* — a per-user grant
of `billing.view` + `expenses.view` + `dashboard.view`, not a blanket
`OTHER_STAFF` role default, since that role is also the demo's "Store
Manager" (inventory-usage-only) — a role-wide grant would leak financial
visibility to every other kind of "other staff" account, not just the one
doing the books. scripts/seed_demo_accounts.py applies this migration's
two new codes (plus the pre-existing `dashboard.view`) as USER-level
overrides to its one named accounts.myclinic@gmail.com demo account only.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-13

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('billing.view', 'billing', 'View invoices and payments tenant-wide, read-only — for a finance/accounts user, not row-scoped like billing.view_own'),
          ('expenses.view', 'expenses', 'View expenses tenant-wide, read-only — for a finance/accounts user, distinct from expenses.manage/expenses.record which also allow writes')
        """
    )
    # Deliberately no role_permissions rows — see this migration's own
    # docstring for why this is applied per-user via permission_overrides,
    # not as a blanket OTHER_STAFF default.


def downgrade() -> None:
    op.execute(
        "DELETE FROM permission_overrides WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('billing.view', 'expenses.view'))"
    )
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('billing.view', 'expenses.view'))")
    op.execute("DELETE FROM permissions WHERE code IN ('billing.view', 'expenses.view')")
