"""Clinic Expenses — PRD-ARCHITECTURE.md §4 (module list item 23), §6.
Verbatim subset of docs/schema/clinic_erp_schema.sql's `expenses` table,
with deliberate additions/deviations, all by direct instruction (this is
the first migration to ever create `expenses`, so no `ALTER TYPE`
gymnastics were needed for the new enum):

1. `category` becomes a real Postgres enum (`expense_category`:
   RENT/UTILITIES/SUPPLIES/SALARY/MAINTENANCE/MARKETING/OTHER) rather than
   the master schema's free-text column — explicitly requested as a fixed
   set, not open text.
2. `payment_mode` is a new column entirely (`expense_payment_mode`:
   CASH/UPI/CARD/BANK_TRANSFER) — the master schema's `expenses` sketch
   never had a payment-method field at all. This is a *different* enum
   from the existing `payment_method` (patient payments: CASH/CARD/UPI/
   NET_BANKING/INSURANCE/OTHER) rather than a reuse of it — an expense
   paid to a vendor has no "insurance" concept, and "BANK_TRANSFER" (the
   term requested here) vs. `payment_method`'s "NET_BANKING" are different
   enough in intent (B2B vendor payment vs. patient-facing payment) not to
   force into one shared enum.
3. `receipt_document_id` is a new nullable `UUID` column with **no FK** —
   the master schema's own comment for this table says a receipt is "a
   `documents` row with owner_type='EXPENSE'," but no generic `documents`
   table has been built by any module yet (Patient EMR's migration 0016
   built the narrower, clinically-scoped `medical_documents` instead,
   which doesn't fit a non-clinical vendor receipt). Same "column
   reserved, FK deferred" pattern as `prescription_items.medicine_id`
   before Pharmacy existed — a future generic Documents module should add
   `REFERENCES documents(id)` via `ALTER TABLE`, not this migration.
4. `vendor` keeps the master schema's column name (same concept as the
   task's "vendor_name" wording, not renamed — same judgment call as
   `lab_test_catalog.price` for the task's "cost").
5. No delete/void endpoint is built — the task's own 3-endpoint spec
   (`POST`/`GET`/`PATCH`) never asked for one, so none was added; revisit
   if a future ask wants expense cancellation.

Permission-matrix deviation, by direct instruction (not a gap-fix): the
PRD §3 matrix gives Receptionist "–" (no access at all) on "General
inventory & expenses." The product owner explicitly asked for
"Receptionist has create and read access (for daily petty-cash logging)."
Rather than widen `expenses.manage` (Owner-only, matches the matrix's "F"
exactly, unchanged) to Receptionist — which would also hand Receptionist
the ability to edit any past expense entry, not what was asked — a new
`expenses.record` (create + read only, no update) is added for
Receptionist. Doctor and every other non-Owner/Receptionist role gets
neither permission, matching "Doctor/Staff have zero access" (task 3) and
the matrix's "–" for everyone but Owner/Other-Staff-configurable.

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-05

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE expense_category AS ENUM ('RENT','UTILITIES','SUPPLIES','SALARY','MAINTENANCE','MARKETING','OTHER')"
    )
    op.execute("CREATE TYPE expense_payment_mode AS ENUM ('CASH','UPI','CARD','BANK_TRANSFER')")

    op.execute(
        """
        CREATE TABLE expenses (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          branch_id            UUID NOT NULL REFERENCES branches(id),
          category             expense_category NOT NULL,
          amount               numeric(12,2) NOT NULL CHECK (amount > 0),
          expense_date         date NOT NULL DEFAULT current_date,
          payment_mode         expense_payment_mode NOT NULL,
          vendor               text,
          notes                text,
          receipt_document_id  UUID,
          recorded_by          UUID NOT NULL REFERENCES users(id),
          created_at           timestamptz NOT NULL DEFAULT now(),
          updated_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_expenses_branch_date ON expenses (tenant_id, branch_id, expense_date)")
    op.execute("CREATE INDEX ix_expenses_category ON expenses (tenant_id, category)")
    op.execute("CREATE TRIGGER trg_expenses_updated_at BEFORE UPDATE ON expenses FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE expenses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE expenses FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON expenses
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (Receptionist create+read) ----------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('expenses.record', 'finance', 'Record and view expenses (no edit) — petty-cash logging')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('RECEPTIONIST', 'expenses.record')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'expenses.record')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'expenses.record'")
    op.execute("DROP TABLE IF EXISTS expenses")
    op.execute("DROP TYPE IF EXISTS expense_payment_mode")
    op.execute("DROP TYPE IF EXISTS expense_category")
