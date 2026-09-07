"""General (Non-Medicine) Inventory — PRD-ARCHITECTURE.md §4 (module list
item 26), §6. Builds `inventory_items`/`inventory_transactions`, sketched
design-only in `docs/schema/clinic_erp_schema.sql` §11 since the file's
original draft but never migrated by any module until now (Pharmacy's own
`medicines`/`medicine_batches`/`pharmacy_inventory_transactions`, migration
0017, are the *medicine*-specific inventory ledger; this is the separate,
non-medicine one — consumables, equipment, lab supplies, office supplies).

Deliberate deviations from the master schema's sketch, all by direct
instruction (this task's own field list):

1. `category` becomes a real `inventory_item_category` enum
   (CONSUMABLE/EQUIPMENT/LAB_SUPPLY/OFFICE) rather than the sketch's free
   text — same "fixed set, not open text" call as Expenses' `category`.
2. `unit` becomes a real `inventory_unit` enum (PIECES/PACKS/BOXES),
   likewise rather than free text — a new deviation, no earlier module had
   a comparable "unit of measure" field to reuse.
3. Column names follow this task's own literal field list rather than the
   sketch's (`current_stock` not `quantity_on_hand`, `min_reorder_level`
   not `reorder_threshold`) — same "use the literal names given" call as
   Pharmacy OTC Sales' `total_amount`/`net_amount` over the sketch's
   `invoice_id`-based design.
4. `cost_per_unit` and `is_active` are new columns the sketch never had —
   same "sketch gap, fill it" pattern as `medicines.reorder_threshold` or
   `strength`/`manufacturer`.
5. No `branch_id` — PRD-ARCHITECTURE.md §26 lists `InventoryItem` among
   branch-scoped operational entities, but this task's own field list
   never mentions one (`item_id, clinic_id, name, category, unit, ...`).
   Kept tenant-wide instead, consistent with `medicines`/`medicine_batches`
   already being tenant-wide despite the PRD's similar original framing for
   those.
6. `inventory_transactions.change_type` is a wholly new
   `inventory_change_type` enum (PURCHASE/USAGE/ADJUSTMENT/RETURN) rather
   than reusing Pharmacy's existing `inventory_txn_type`
   (RECEIVE/DISPENSE/SALE/ADJUST/EXPIRE_WRITE_OFF) — this task's own
   4-value vocabulary is different enough (and this is a different domain:
   non-medicine consumables/equipment, not medicine batches) that forcing
   a shared enum would mean one of the two domains inheriting values that
   don't make sense for it. First creation, no `ALTER TYPE` needed.
7. `quantity` stores the caller's submitted magnitude as-is (always
   positive for PURCHASE/USAGE/RETURN, either sign for ADJUSTMENT) rather
   than a pre-signed `quantity_delta` — `change_type` plus `quantity`
   together fully describe the movement; the app derives the signed delta
   applied to `current_stock` (see `InventoryService.record_transaction`).
   `reference_id` is a nullable UUID with no FK — same "column reserved,
   no target table specified" pattern as `receipt_document_id` (Expenses)
   before a generic Documents module exists.

No new tables' worth of RBAC gap here — `inventory.manage` (Owner) has
existed, unused by any endpoint, since migration 0001. **This module's
RBAC is a direct product-owner deviation from the PRD §3 matrix, not a
gap-fix**: the matrix's "General inventory & expenses" row gives everyone
but Owner "–" (Other Staff gets a configurable "C"). The product owner
explicitly asked for Receptionist/Nurse/(Other Staff, the matrix's own
"Staff" tier) to read items and log `USAGE` transactions specifically —
not `PURCHASE`/`ADJUSTMENT`/`RETURN`, which stay Owner-only — and for
Doctor to have read-only access. Two new permissions: `inventory.view`
(Doctor, read-only) and `inventory.record_usage` (Receptionist/Nurse/Other
Staff, read + `USAGE`-only write, enforced at the service layer since a
single route handles every `change_type`, the same "shared route,
role-checked in the service" pattern Expenses' `update_expense` avoided by
using a *separate* permission-gated route instead — this module can't do
that split since all four `change_type`s share one endpoint).

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-07

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE inventory_item_category AS ENUM ('CONSUMABLE','EQUIPMENT','LAB_SUPPLY','OFFICE')")
    op.execute("CREATE TYPE inventory_unit AS ENUM ('PIECES','PACKS','BOXES')")
    op.execute("CREATE TYPE inventory_change_type AS ENUM ('PURCHASE','USAGE','ADJUSTMENT','RETURN')")

    op.execute(
        """
        CREATE TABLE inventory_items (
          id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          name               text NOT NULL,
          category           inventory_item_category NOT NULL,
          unit               inventory_unit NOT NULL,
          current_stock      numeric(10,2) NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
          min_reorder_level  numeric(10,2) NOT NULL DEFAULT 0,
          cost_per_unit      numeric(10,2) NOT NULL DEFAULT 0,
          is_active          boolean NOT NULL DEFAULT true,
          created_at         timestamptz NOT NULL DEFAULT now(),
          updated_at         timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_inventory_items_category ON inventory_items (tenant_id, category)")
    op.execute("CREATE TRIGGER trg_inventory_items_updated_at BEFORE UPDATE ON inventory_items FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE inventory_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inventory_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON inventory_items
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE inventory_transactions (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id    UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          item_id      UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
          change_type  inventory_change_type NOT NULL,
          quantity     numeric(10,2) NOT NULL CHECK (quantity <> 0),
          reference_id UUID,
          performed_by UUID NOT NULL REFERENCES users(id),
          notes        text,
          created_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_inventory_txn_item ON inventory_transactions (item_id, created_at)")
    op.execute("ALTER TABLE inventory_transactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE inventory_transactions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON inventory_transactions
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (Doctor read-only; Receptionist/Nurse/Other Staff read + USAGE-only write) ---
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('inventory.view', 'inventory', 'Read-only access to general (non-pharmacy) inventory items and low-stock alerts'),
          ('inventory.record_usage', 'inventory', 'Read general inventory items/alerts and log USAGE transactions only — PURCHASE/ADJUSTMENT/RETURN remain inventory.manage-only')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('DOCTOR','inventory.view'),
          ('RECEPTIONIST','inventory.record_usage'),
          ('NURSE','inventory.record_usage'),
          ('OTHER_STAFF','inventory.record_usage')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('inventory.view', 'inventory.record_usage'))
        """
    )
    op.execute("DELETE FROM permissions WHERE code IN ('inventory.view', 'inventory.record_usage')")
    op.execute("DROP TABLE IF EXISTS inventory_transactions")
    op.execute("DROP TABLE IF EXISTS inventory_items")
    op.execute("DROP TYPE IF EXISTS inventory_change_type")
    op.execute("DROP TYPE IF EXISTS inventory_unit")
    op.execute("DROP TYPE IF EXISTS inventory_item_category")
