"""Pharmacy & Inventory Management — PRD-ARCHITECTURE.md §4 (module list
items 24/25), §18 (Pharmacy Architecture), §6. Verbatim subset of
docs/schema/clinic_erp_schema.sql's `medicines`/`medicine_batches`/
`pharmacy_inventory_transactions` tables (`inventory_txn_type` enum
included), with deliberate additions/deviations, all by direct
instruction:

1. `medicines` gains `strength` and `manufacturer` (explicitly requested;
   the master schema's sketch only had name/generic_name/category/
   dosage_form/unit_price/sku) and `reorder_threshold` (explicitly
   requested — "reorder alert thresholds" — the master schema only modeled
   that concept on the separate, generic `InventoryItem` entity, not on a
   medicine specifically). Same "sketch gap, fill it, document it" pattern
   as `route` on `prescription_items` (migration 0013) or `users.
   first_name` (migration 0005).
2. This module deliberately does NOT build `pharmacy_sales` (OTC sales not
   tied to a prescription) — task scope is catalog + batch inventory +
   prescription-linked dispensing only; a future module can add OTC POS
   without touching anything here.
3. **Fulfills a promise migration 0013 made**: `prescription_items.
   medicine_id` was created without its `REFERENCES medicines(id)` FK
   because `medicines` didn't exist yet, with an explicit note to add the
   constraint once it did. Done here via `ALTER TABLE`. Also updates
   `app/modules/consultation/schemas.py::PrescriptionItemCreateRequest`
   (a real, deliberate change to an already-shipped module — not a
   regression) to accept an optional `medicine_id`, validated against the
   tenant's catalog — without this, dispensing "against a prescription"
   would be impossible, since no prescription item could ever reference a
   real medicine.

No `role_permissions` seed gap for the two permissions the master schema
already had (`pharmacy.manage_catalog`, `pharmacy.dispense` — both
Owner/Pharmacy Staff since migration 0001, matching the PRD §3 matrix's
"F" for both roles on both rows exactly). What *was* missing: a read-only
permission for Doctor, who the matrix gives "R" on "Pharmacy catalog &
inventory" (not dispensing) — migration 0001 granted Doctor nothing here
at all. Fixed by adding `pharmacy.view_catalog`, granted to Owner,
Pharmacy Staff, and Doctor — a real matrix gap, same shape as four earlier
ones this session, not a deviation.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE inventory_txn_type AS ENUM ('RECEIVE','DISPENSE','SALE','ADJUST','EXPIRE_WRITE_OFF')")

    op.execute(
        """
        CREATE TABLE medicines (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          name              text NOT NULL,
          generic_name      text,
          category          text,
          dosage_form       text,
          strength          text,
          manufacturer      text,
          unit_price        numeric(10,2) NOT NULL DEFAULT 0,
          sku               text,
          reorder_threshold int NOT NULL DEFAULT 0,
          is_active         boolean NOT NULL DEFAULT true,
          created_at        timestamptz NOT NULL DEFAULT now(),
          updated_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_medicines_sku ON medicines (tenant_id, sku) WHERE sku IS NOT NULL")
    op.execute("CREATE TRIGGER trg_medicines_updated_at BEFORE UPDATE ON medicines FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE medicines ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE medicines FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON medicines
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE medicine_batches (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          medicine_id      UUID NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
          batch_number     text NOT NULL,
          expiry_date      date NOT NULL,
          quantity_on_hand int NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
          cost_price       numeric(10,2),
          created_at       timestamptz NOT NULL DEFAULT now(),
          updated_at       timestamptz NOT NULL DEFAULT now(),
          UNIQUE (medicine_id, batch_number)
        )
        """
    )
    op.execute("CREATE INDEX ix_batches_expiry ON medicine_batches (tenant_id, expiry_date)")
    op.execute("CREATE TRIGGER trg_medicine_batches_updated_at BEFORE UPDATE ON medicine_batches FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE medicine_batches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE medicine_batches FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON medicine_batches
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE pharmacy_inventory_transactions (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          batch_id       UUID NOT NULL REFERENCES medicine_batches(id),
          type           inventory_txn_type NOT NULL,
          quantity_delta int NOT NULL,
          reference_type text,
          reference_id   UUID,
          performed_by   UUID NOT NULL REFERENCES users(id),
          notes          text,
          created_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_pharm_txn_batch ON pharmacy_inventory_transactions (batch_id, created_at)")
    op.execute("ALTER TABLE pharmacy_inventory_transactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pharmacy_inventory_transactions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON pharmacy_inventory_transactions
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Fulfill migration 0013's deferred FK ------------------------------
    op.execute(
        "ALTER TABLE prescription_items ADD CONSTRAINT fk_prescription_items_medicine FOREIGN KEY (medicine_id) REFERENCES medicines(id)"
    )

    # --- Permission matrix gap fix (Doctor read access) --------------------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('pharmacy.view_catalog', 'pharmacy', 'View medicine catalog and batch stock levels — read-only')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','pharmacy.view_catalog'),
          ('PHARMACY_STAFF','pharmacy.view_catalog'),
          ('DOCTOR','pharmacy.view_catalog')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'pharmacy.view_catalog')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'pharmacy.view_catalog'")
    op.execute("ALTER TABLE prescription_items DROP CONSTRAINT IF EXISTS fk_prescription_items_medicine")
    op.execute("DROP TABLE IF EXISTS pharmacy_inventory_transactions")
    op.execute("DROP TABLE IF EXISTS medicine_batches")
    op.execute("DROP TABLE IF EXISTS medicines")
    op.execute("DROP TYPE IF EXISTS inventory_txn_type")
