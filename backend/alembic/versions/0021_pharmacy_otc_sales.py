"""Pharmacy OTC / Retail Sales — PRD-ARCHITECTURE.md §4/§18/§6. Builds the
`pharmacy_sales`/`pharmacy_sale_items` tables that migration 0017's own
docstring explicitly deferred ("This module deliberately does NOT build
`pharmacy_sales`... a future module can add OTC POS without touching
anything here") and that `docs/schema/clinic_erp_schema.sql` had already
sketched as "design-only."

Deliberate deviations from the master schema's `pharmacy_sales` sketch, all
by direct instruction (this task's own 10-field spec):

1. The master schema's sketch links a sale to `patient_id`/`invoice_id`
   (assuming every OTC sale is either a registered patient or eventually
   reconciled into Billing). This task asked for `customer_name`/
   `customer_phone` free text instead and an explicit `total_amount`/
   `discount_amount`/`net_amount`/`payment_mode`/`status` on the sale row
   itself — i.e. the sale row *is* the receipt, not a pointer to one build
   elsewhere. No `patient_id`/`invoice_id` column exists here; a future
   module can add that reconciliation without touching this table, same
   "future module, not this one" judgment migration 0017 already made.
2. No `branch_id` — consistent with `medicines`/`medicine_batches`
   themselves being tenant-wide, not branch-scoped (migration 0017 never
   added branch scoping to inventory), a counter sale drawing from that
   same tenant-wide stock has no natural branch to attach to either.
3. `payment_mode` reuses the existing `payment_method` enum (CASH/CARD/
   UPI/NET_BANKING/INSURANCE/OTHER, migration 0014) rather than inventing
   a new one — this is a customer-facing payment, the same domain as an
   `Invoice`'s `Payment.method`, unlike Expenses' vendor-facing
   `expense_payment_mode` (migration 0020), which was deliberately kept
   separate for the opposite reason.
4. `status` is a new `pharmacy_sale_status` enum (`PAID`/`REFUNDED`, this
   task's own two values) — first migration to create it, no `ALTER TYPE`
   needed. **Only `PAID` is reachable from this migration's endpoints** —
   this task's own 3-endpoint spec (checkout, list, detail) never asked
   for a refund endpoint, so none was built; `REFUNDED` is a reserved,
   not-yet-wired value, same "column/value reserved, endpoint deferred"
   pattern as `receipt_document_id` (Expenses) or `medicine_id` before
   Pharmacy existed.
5. Stock deduction reuses `inventory_txn_type`'s existing `SALE` member
   (added in migration 0017, unused until now — the enum already
   anticipated this exact call site) rather than adding a new type.

`pharmacy_sale_items.batch_id` is NOT NULL — every line is already the
FEFO-resolved batch a unit was actually drawn from (mirroring
`DispenseAllocation`'s shape from prescription dispensing), so one cart
line spanning two batches becomes two `pharmacy_sale_items` rows, not one
row with an ambiguous batch. `unit_price` is copied from `Medicine.
unit_price` at sale time (a receipt must not silently reprice itself if
the catalog price changes later) — same "snapshot, don't recompute"
reasoning as `invoice_line_items.unit_price`.

Permission-matrix deviation, by direct instruction (not a gap-fix): the
PRD §3 matrix marks "Pharmacy dispensing / POS" as Owner/Pharmacy Staff
only ("F"), Receptionist "–". The product owner explicitly asked for
Receptionist to also have create+view access to OTC sales specifically —
NOT to prescription dispensing, so widening `pharmacy.dispense` itself
(which also gates `/pharmacy/dispense`) would have overshot the ask. A new
`pharmacy.sell_otc` (Receptionist only) is added instead, and the sales
routes are gated by `require_any_permission("pharmacy.dispense",
"pharmacy.sell_otc")` — Owner/Pharmacy Staff reach them via their existing
grant, Receptionist via the new one, same `require_any_permission` pattern
Billing/Reports/Lab already established for "two different permission
codes reach the same route." Doctor/Nurse get neither — zero access,
matching the matrix's "–" for the POS row exactly (Doctor's existing
`pharmacy.view_catalog` is a *catalog* read grant, a different matrix row,
and deliberately not reused here).

Gated behind `require_feature_flag("features.pharmacy_enabled")` — the
generic mechanism `app/api/deps.py::require_feature_flag()` already
provides (first used by Lab, migration 0018) reused with a new flag key;
no new column/table for the flag itself, an Owner opts in via the existing
generic `PUT /api/v1/clinics/me/settings/{key}` endpoint.

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-07

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE pharmacy_sale_status AS ENUM ('PAID','REFUNDED')")

    op.execute(
        """
        CREATE TABLE pharmacy_sales (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          customer_name   text,
          customer_phone  text,
          total_amount    numeric(12,2) NOT NULL CHECK (total_amount >= 0),
          discount_amount numeric(12,2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
          net_amount      numeric(12,2) NOT NULL CHECK (net_amount >= 0),
          payment_mode    payment_method NOT NULL,
          status          pharmacy_sale_status NOT NULL DEFAULT 'PAID',
          created_by      UUID NOT NULL REFERENCES users(id),
          created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_pharmacy_sales_date ON pharmacy_sales (tenant_id, created_at)")
    op.execute("CREATE INDEX ix_pharmacy_sales_payment_mode ON pharmacy_sales (tenant_id, payment_mode)")
    op.execute("ALTER TABLE pharmacy_sales ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pharmacy_sales FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON pharmacy_sales
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE pharmacy_sale_items (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          sale_id     UUID NOT NULL REFERENCES pharmacy_sales(id) ON DELETE CASCADE,
          medicine_id UUID NOT NULL REFERENCES medicines(id),
          batch_id    UUID NOT NULL REFERENCES medicine_batches(id),
          quantity    int NOT NULL CHECK (quantity > 0),
          unit_price  numeric(10,2) NOT NULL,
          total_price numeric(12,2) NOT NULL,
          created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_pharmacy_sale_items_sale ON pharmacy_sale_items (sale_id)")
    op.execute("ALTER TABLE pharmacy_sale_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pharmacy_sale_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON pharmacy_sale_items
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (Receptionist create+view on OTC sales only) ---
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('pharmacy.sell_otc', 'pharmacy', 'Create/view OTC counter sales (not tied to a prescription) — Receptionist-only addition; Owner/Pharmacy Staff already reach the same routes via pharmacy.dispense')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('RECEPTIONIST', 'pharmacy.sell_otc')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'pharmacy.sell_otc')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'pharmacy.sell_otc'")
    op.execute("DROP TABLE IF EXISTS pharmacy_sale_items")
    op.execute("DROP TABLE IF EXISTS pharmacy_sales")
    op.execute("DROP TYPE IF EXISTS pharmacy_sale_status")
