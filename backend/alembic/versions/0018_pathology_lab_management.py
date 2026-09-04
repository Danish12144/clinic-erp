"""Pathology / Diagnostic Lab Management — PRD-ARCHITECTURE.md §4 (module
list items 26/27), §5.5, §19 (Laboratory Architecture), §6. Verbatim
subset of docs/schema/clinic_erp_schema.sql's `lab_test_catalog`/
`lab_orders`/`lab_results` tables (`lab_order_status`/`lab_result_flag`
enums included), with deliberate additions/deviations, all by direct
instruction:

1. `lab_order_status` is created here for the first time (no earlier
   migration touched Lab) as `('ORDERED','SAMPLE_COLLECTED','RESULTED',
   'COMPLETED','CANCELLED')` rather than the master schema's own narrative
   (§5.5/§19: "SAMPLE_COLLECTED → PROCESSING → COMPLETED") — the product
   owner explicitly asked for `RESULTED` in place of `PROCESSING`, plus an
   explicit `CANCELLED` branch (already in the DDL's own enum, just never
   mentioned in the prose workflow). `RESULTED` sits between "results
   entered" and `COMPLETED` ("results finalized/locked, visible to Doctor
   and, once patient-portal-visible, Patient") — matching the master
   schema's own "report is finalized... becomes visible" language, just
   naming the intermediate state explicitly instead of leaving it implicit
   in `PROCESSING`.
2. `lab_test_catalog` gains `test_code`, `specimen_type`, and
   `turnaround_hours` (explicitly requested; the master schema's sketch
   only had name/category/price/reference_ranges) — same "sketch gap, fill
   it, document it" pattern as `route` on `prescription_items` or
   `strength`/`manufacturer` on `medicines`. `reference_ranges` changes
   shape from the master schema's bare JSONB object (`'{}'::jsonb`) to a
   JSONB *array* of `{min, max, unit, sex, age_min, age_max}` entries,
   default `'[]'::jsonb` — still "data, not code" per the master schema's
   own §19 architectural principle (a clinic edits this without a
   deployment), just structured enough to actually support automatic
   out-of-range flagging (task 3) and per-sex/age variation (task 1) at
   once, rather than leaving the object's internal shape undefined.
3. `lab_orders` gains a direct `patient_id` (denormalized off `encounter_id`
   for the row-scoping/filtering this module needs without a join every
   time, same reasoning `vitals`/`medical_documents` already used) and a
   separate `doctor_id` (the clinically-ordering doctor — distinct from
   `ordered_by`, the literal actor who submitted the order via the API,
   which may be Owner or Lab Staff keying it in on the doctor's behalf),
   plus `resulted_at`/`cancelled_at`/`cancelled_reason` mirroring the
   existing `sample_collected_at`/`completed_at` pattern for the new
   `RESULTED` state and the state-transition-with-a-reason convention
   already used by `Appointment`/`Invoice`.

No integration with `Invoice`/`InvoiceLineItem` is built here — the PRD's
own workflow narrative (§5.5) mentions "billed via the same Invoice
mechanism," but this task's own scope (its 5-point spec) never asked for
it, unlike Billing's explicit "auto-generate from a Consultation fee." Out
of scope for this pass, same as `pharmacy_sales` was for Pharmacy.

**Tenant feature gate** (task 4): a new generic `app.api.deps.
require_feature_flag()` dependency factory (reusable by any future
feature-gated module, not Lab-specific) checks a `TenantSetting` — key
`features.lab_enabled`, default **off** until an Owner explicitly opts in
via the existing generic `PUT /api/v1/clinics/me/settings/{key}` endpoint
(Tenancy module, already built — no new settings endpoint needed). Every
Lab route requires this in addition to its permission check.

Permission-matrix gap fix (same shape as six earlier ones this session,
not a deviation): `lab.manage_catalog` (Owner)/`lab.order` (Owner/Doctor/
Lab Staff)/`lab.enter_results` (Owner/Lab Staff) already matched the PRD §3
matrix exactly since migration `0001` — task 5's own framing ("Lab
Technician/Owner manage orders and results") confirms catalog management
staying Owner-only was intentional, not a gap. What *was* missing: a read
permission for the "Lab result entry & reports" row's Doctor "R" and
Patient "O (read)" cells — migration `0001` granted neither role anything
lab-related at all. Fixed by adding `lab.view_results`, granted to Owner,
Doctor, Lab Staff, and Patient (Patient additionally scoped to their own
`patient_id` *and* `COMPLETED`-only orders at the service layer — "reads
completed reports," not pending ones, per task 5).

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE lab_order_status AS ENUM ('ORDERED','SAMPLE_COLLECTED','RESULTED','COMPLETED','CANCELLED')")
    op.execute("CREATE TYPE lab_result_flag AS ENUM ('NORMAL','LOW','HIGH','CRITICAL')")

    op.execute(
        """
        CREATE TABLE lab_test_catalog (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          name              text NOT NULL,
          test_code         text,
          category          text,
          specimen_type     text,
          turnaround_hours  int,
          price             numeric(10,2) NOT NULL DEFAULT 0,
          reference_ranges  jsonb NOT NULL DEFAULT '[]'::jsonb,
          is_active         boolean NOT NULL DEFAULT true,
          created_at        timestamptz NOT NULL DEFAULT now(),
          updated_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_lab_test_code ON lab_test_catalog (tenant_id, test_code) WHERE test_code IS NOT NULL")
    op.execute("CREATE TRIGGER trg_lab_test_catalog_updated_at BEFORE UPDATE ON lab_test_catalog FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE lab_test_catalog ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lab_test_catalog FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON lab_test_catalog
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE lab_orders (
          id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id           UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          encounter_id        UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
          patient_id          UUID NOT NULL REFERENCES patients(id),
          doctor_id           UUID REFERENCES users(id),
          test_id             UUID NOT NULL REFERENCES lab_test_catalog(id),
          ordered_by          UUID NOT NULL REFERENCES users(id),
          status              lab_order_status NOT NULL DEFAULT 'ORDERED',
          ordered_at          timestamptz NOT NULL DEFAULT now(),
          sample_collected_at timestamptz,
          resulted_at         timestamptz,
          completed_at        timestamptz,
          cancelled_at        timestamptz,
          cancelled_reason    text,
          created_at          timestamptz NOT NULL DEFAULT now(),
          updated_at          timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_lab_orders_encounter ON lab_orders (encounter_id)")
    op.execute("CREATE INDEX ix_lab_orders_patient ON lab_orders (tenant_id, patient_id, created_at)")
    op.execute("CREATE INDEX ix_lab_orders_doctor ON lab_orders (doctor_id)")
    op.execute("CREATE TRIGGER trg_lab_orders_updated_at BEFORE UPDATE ON lab_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE lab_orders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lab_orders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON lab_orders
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE lab_results (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          lab_order_id    UUID NOT NULL REFERENCES lab_orders(id) ON DELETE CASCADE,
          parameter       text NOT NULL,
          value           text NOT NULL,
          unit            text,
          reference_range text,
          flag            lab_result_flag NOT NULL DEFAULT 'NORMAL',
          entered_by      UUID NOT NULL REFERENCES users(id),
          finalized_at    timestamptz,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_lab_results_order ON lab_results (lab_order_id)")
    op.execute("ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lab_results FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON lab_results
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix gap fix (Doctor + Patient read access) --------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('lab.view_results', 'laboratory', 'View lab orders/results — Patient further scoped to own COMPLETED orders')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','lab.view_results'),
          ('DOCTOR','lab.view_results'),
          ('LAB_STAFF','lab.view_results'),
          ('PATIENT','lab.view_results')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'lab.view_results')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'lab.view_results'")
    op.execute("DROP TABLE IF EXISTS lab_results")
    op.execute("DROP TABLE IF EXISTS lab_orders")
    op.execute("DROP TABLE IF EXISTS lab_test_catalog")
    op.execute("DROP TYPE IF EXISTS lab_result_flag")
    op.execute("DROP TYPE IF EXISTS lab_order_status")
