"""Doctor Consultation, Clinical Notes & E-Prescription —
PRD-ARCHITECTURE.md §4 module list items 17/18/19, §5.1, §6. Verbatim
subset of docs/schema/clinic_erp_schema.sql's `consultations`/
`prescriptions`/`prescription_items` tables, with one deliberate deviation:
`prescription_items.medicine_id` is created WITHOUT its `REFERENCES
medicines(id)` foreign key, because `medicines` doesn't exist yet (the
Pharmacy module hasn't been built) — a migration can't reference a table
that doesn't exist. The column stays (so no future migration needs to add
it), and a future Pharmacy migration should `ALTER TABLE prescription_items
ADD CONSTRAINT ... FOREIGN KEY (medicine_id) REFERENCES medicines(id)` once
that table exists. Until then, the API only accepts free-text medicines —
see app/modules/consultation/schemas.py.

`consultations` drives Encounter's OPEN -> IN_CONSULTATION -> COMPLETED
transitions (this module owns that transition, as flagged by Check-in's
migration 0011 docstring). `prescriptions` is immutable-with-supersession
(PRD §5.4/§5.7) — same `prevent_update_delete()` mechanism `vitals` uses,
reserved since migration 0001; `prescription_items` is NOT append-only
(its `dispensed_quantity` is mutable by the future Pharmacy module).

Permission matrix deviation, by explicit direct instruction (not a
seed-vs-matrix gap fix like every previous correction in this file's
history): the PRD §3 matrix gives Owner only "R" and Nurse "–" for both
"Consultation, diagnosis, clinical notes" and "E-prescription" (Doctor
"F own" only). The product owner explicitly asked for "Doctor/Owner write,
Doctor/Owner/Nurse read" instead — Owner now also gets
`consultation.manage`/`prescription.manage` (write, alongside Doctor, both
still recorded as `doctor_id = the acting user`, not row-scoped since
Owner's access is tenant-wide by role), and `consultation.view`/
`prescription.view` (new, read) go to Owner, Doctor, and Nurse — Doctor's
read is row-scoped to their own `doctor_id` at the service layer (matching
the matrix's "F (own)"); Owner/Nurse reads are tenant-wide, unscoped, same
"no (own) qualifier in the matrix => no row-scoping" reasoning Check-in
(migration 0011) and Vitals (migration 0012) already established. This is
a considered product decision, not a bug fix — flagged here in case it
needs revisiting, not silently absorbed into "gap fixed."

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE consultations (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          encounter_id    UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
          doctor_id       UUID NOT NULL REFERENCES users(id),
          chief_complaint text,
          clinical_notes  text,
          diagnosis_text  text,
          icd10_code      text,
          started_at      timestamptz,
          ended_at        timestamptz,
          created_at      timestamptz NOT NULL DEFAULT now(),
          updated_at      timestamptz NOT NULL DEFAULT now(),
          UNIQUE (encounter_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_consultations_doctor ON consultations (doctor_id, created_at)")
    op.execute(
        "CREATE TRIGGER trg_consultations_updated_at BEFORE UPDATE ON consultations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE consultations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE consultations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON consultations
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE prescriptions (
          id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id                  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          encounter_id               UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
          doctor_id                  UUID NOT NULL REFERENCES users(id),
          supersedes_prescription_id UUID REFERENCES prescriptions(id),
          issued_at                  timestamptz NOT NULL DEFAULT now(),
          created_at                 timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_prescriptions_encounter ON prescriptions (encounter_id)")
    op.execute("CREATE INDEX ix_prescriptions_doctor ON prescriptions (doctor_id, issued_at)")
    op.execute(
        "CREATE TRIGGER trg_prescriptions_immutable BEFORE UPDATE OR DELETE ON prescriptions "
        "FOR EACH ROW EXECUTE FUNCTION prevent_update_delete()"
    )
    op.execute("ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE prescriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON prescriptions
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON prescriptions FROM app_user")

    op.execute(
        """
        CREATE TABLE prescription_items (
          id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id              UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          prescription_id        UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
          medicine_id            UUID,
          medicine_name_freetext text,
          dosage                 text,
          frequency              text,
          duration               text,
          route                  text,
          prescribed_quantity    int NOT NULL,
          dispensed_quantity     int NOT NULL DEFAULT 0,
          instructions           text,
          created_at             timestamptz NOT NULL DEFAULT now(),
          updated_at             timestamptz NOT NULL DEFAULT now(),
          CHECK (medicine_id IS NOT NULL OR medicine_name_freetext IS NOT NULL),
          CHECK (dispensed_quantity <= prescribed_quantity)
        )
        """
    )
    op.execute("CREATE INDEX ix_prescription_items_prescription ON prescription_items (prescription_id)")
    op.execute(
        "CREATE TRIGGER trg_prescription_items_updated_at BEFORE UPDATE ON prescription_items "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE prescription_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE prescription_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON prescription_items
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (by direct instruction — see module
    # docstring above, not a seed-vs-matrix gap fix) ---------------------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('consultation.view', 'clinical', 'View consultations/clinical notes — Doctor scoped to own, Owner/Nurse tenant-wide'),
          ('prescription.view', 'clinical', 'View prescriptions — Doctor scoped to own, Owner/Nurse tenant-wide')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','consultation.manage'), ('OWNER','prescription.manage'),
          ('OWNER','consultation.view'), ('OWNER','prescription.view'),
          ('DOCTOR','consultation.view'), ('DOCTOR','prescription.view'),
          ('NURSE','consultation.view'), ('NURSE','prescription.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('consultation.view', 'prescription.view'))
           OR (role_id, permission_id) IN (
             SELECT r.id, p.id FROM roles r, permissions p
             WHERE (r.code, p.code) IN (('OWNER','consultation.manage'), ('OWNER','prescription.manage'))
           )
        """
    )
    op.execute("DELETE FROM permissions WHERE code IN ('consultation.view', 'prescription.view')")
    op.execute("DROP TABLE IF EXISTS prescription_items")
    op.execute("DROP TABLE IF EXISTS prescriptions")
    op.execute("DROP TABLE IF EXISTS consultations")
