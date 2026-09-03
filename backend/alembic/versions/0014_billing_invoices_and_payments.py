"""Billing, Invoices & Payments — PRD-ARCHITECTURE.md §4 module list items
20/21/22, §5.1 step 11-12, §6, §17. Verbatim subset of
docs/schema/clinic_erp_schema.sql's `invoices`/`invoice_line_items`/
`payments` tables, with two deliberate deviations from the master schema,
both by direct product-owner instruction (not PRD gap-fixes):

1. `invoice_status` is created here for the first time (no earlier
   migration touched Billing) as `('DRAFT','ISSUED','PARTIALLY_PAID',
   'PAID','VOID')` rather than the master schema's `('UNPAID',
   'PARTIALLY_PAID','PAID','VOID')` — the product owner explicitly asked
   for a DRAFT -> ISSUED -> PAID/PARTIALLY_PAID/VOID state machine.
   `ISSUED` plays `UNPAID`'s old role (an invoice with a locked line-item
   set, awaiting payment); `DRAFT` is new — line items are freely
   add/edit/remove-able only in this state, matching the PRD's own
   architecture note ("keep the common case — editing a draft invoice
   line before payment — simple"). Status is still always *derived* from
   recorded payments once ISSUED, never set directly by the app (same
   invariant the master schema's own comment documents).
2. `payment_method` adds `NET_BANKING` (explicitly requested) to the
   master schema's `('CASH','CARD','UPI','INSURANCE','OTHER')` — kept
   the existing values rather than replacing them, since `INSURANCE` is
   load-bearing elsewhere in the PRD (§17's insurance/co-pay tracking).

Two schema gap-fills, same category as `users.first_name` / prescription
`route` in earlier modules: `invoice_line_items.updated_at` (the master
schema omitted it, but in-place editing of a DRAFT line item is exactly
the "simple common case" §30's architecture notes call out) and
`payments.notes` (the master schema's own narrative promises "a Payment
with negative amount + reason" for refunds, but the DDL had no column to
hold that reason).

`payments` is NOT attached to `prevent_update_delete()` — per the master
schema's own architecture notes, only `vitals`/`prescriptions`/
`audit_logs` get that DB-level guarantee; payments (like
`pharmacy_inventory_transactions`) are "insert-mostly but not DB-locked,"
enforced by app convention (a refund is a new negative-amount row, never
an edit) rather than a trigger. This module's repository has no
update/delete method for `Payment` either way.

No permission changes needed — migration `0001`'s seed for `billing.manage`
(Owner/Receptionist), `billing.view_own` (Doctor/Patient), and
`payments.record` (Owner/Receptionist) already matches the PRD §3 matrix
exactly for both the "Billing & invoices" and "Payments" rows, unlike
every other clinical module built so far.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE invoice_status AS ENUM ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','VOID')")
    op.execute("CREATE TYPE invoice_line_source AS ENUM ('CONSULTATION','PROCEDURE','PHARMACY','LAB','OTHER')")
    op.execute("CREATE TYPE payment_method AS ENUM ('CASH','CARD','UPI','NET_BANKING','INSURANCE','OTHER')")

    op.execute(
        """
        CREATE TABLE invoices (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          branch_id     UUID NOT NULL REFERENCES branches(id),
          encounter_id  UUID REFERENCES encounters(id),
          patient_id    UUID NOT NULL REFERENCES patients(id),
          subtotal      numeric(12,2) NOT NULL DEFAULT 0,
          tax           numeric(12,2) NOT NULL DEFAULT 0,
          discount      numeric(12,2) NOT NULL DEFAULT 0,
          total         numeric(12,2) NOT NULL DEFAULT 0,
          status        invoice_status NOT NULL DEFAULT 'DRAFT',
          voided_at     timestamptz,
          voided_reason text,
          created_at    timestamptz NOT NULL DEFAULT now(),
          updated_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_invoices_patient ON invoices (patient_id)")
    op.execute("CREATE INDEX ix_invoices_branch_date ON invoices (branch_id, created_at)")
    op.execute("CREATE INDEX ix_invoices_encounter ON invoices (encounter_id)")
    op.execute(
        "CREATE TRIGGER trg_invoices_updated_at BEFORE UPDATE ON invoices "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE invoices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoices FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON invoices
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE invoice_line_items (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          invoice_id  UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
          source_type invoice_line_source NOT NULL,
          source_id   UUID,
          description text NOT NULL,
          quantity    numeric(10,2) NOT NULL DEFAULT 1,
          unit_price  numeric(10,2) NOT NULL,
          total       numeric(12,2) NOT NULL,
          created_at  timestamptz NOT NULL DEFAULT now(),
          updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_invoice_line_items_invoice ON invoice_line_items (invoice_id)")
    op.execute(
        "CREATE TRIGGER trg_invoice_line_items_updated_at BEFORE UPDATE ON invoice_line_items "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE invoice_line_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoice_line_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON invoice_line_items
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE payments (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          invoice_id        UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
          amount            numeric(12,2) NOT NULL,
          method            payment_method NOT NULL,
          gateway_reference text,
          notes             text,
          recorded_by       UUID NOT NULL REFERENCES users(id),
          recorded_at       timestamptz NOT NULL DEFAULT now(),
          created_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_payments_invoice ON payments (invoice_id)")
    op.execute("ALTER TABLE payments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON payments
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS payments")
    op.execute("DROP TABLE IF EXISTS invoice_line_items")
    op.execute("DROP TABLE IF EXISTS invoices")
    op.execute("DROP TYPE IF EXISTS payment_method")
    op.execute("DROP TYPE IF EXISTS invoice_line_source")
    op.execute("DROP TYPE IF EXISTS invoice_status")
