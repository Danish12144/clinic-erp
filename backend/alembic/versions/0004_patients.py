"""Patient Management module: the `patients` table. Verbatim subset of
docs/schema/clinic_erp_schema.sql section 6 (patients only — appointments/
encounters/vitals/etc. belong to later modules).

Also corrects two gaps between migration 0001's seed data and the PRD §3
permission matrix, both discovered while building this module (caught by
this module's own integration tests failing with unexpected 403s):
- Lab Staff and Pharmacy Staff have read ("R") access to patient
  registration/search per the matrix (they need to identify a patient to
  order a test or dispense a prescription), but neither role was ever
  granted `patients.view_demographics`.
- Owner has full ("F") patient-EMR access per the matrix, and was granted
  `patients.view_emr` accordingly — but not `patients.view_demographics`,
  which this module's read endpoints actually check. Doctor got both
  permissions granted in migration 0001; Owner should have too.
Fixing both here rather than editing an already-applied migration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Needed for fuzzy name search (func.similarity / the trigram GIN
    # index below) — not required by any table created so far.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute(
        """
        CREATE TABLE patients (
          id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          user_id            UUID REFERENCES users(id),
          mrn                text NOT NULL,
          first_name         text NOT NULL,
          last_name          text,
          gender             text CHECK (gender IN ('Male','Female','Other')),
          date_of_birth      date,
          phone              text,
          email              text,
          blood_group        text,
          allergies          text[] NOT NULL DEFAULT '{}',
          chronic_conditions text[] NOT NULL DEFAULT '{}',
          emergency_contact  jsonb,
          address            text,
          created_at         timestamptz NOT NULL DEFAULT now(),
          updated_at         timestamptz NOT NULL DEFAULT now(),
          deleted_at         timestamptz,
          UNIQUE (tenant_id, mrn)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_patients_user ON patients (user_id) WHERE user_id IS NOT NULL")
    op.execute("CREATE INDEX ix_patients_tenant_phone ON patients (tenant_id, phone)")
    op.execute(
        "CREATE INDEX ix_patients_name_trgm ON patients "
        "USING gin ((first_name || ' ' || coalesce(last_name, '')) gin_trgm_ops)"
    )

    op.execute("CREATE TRIGGER trg_patients_updated_at BEFORE UPDATE ON patients FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE patients ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patients FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON patients
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix correction (see module docstring above) ---------
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('LAB_STAFF','patients.view_demographics'),
          ('PHARMACY_STAFF','patients.view_demographics'),
          ('OWNER','patients.view_demographics')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE (role_id, permission_id) IN (
          SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
            ('LAB_STAFF','patients.view_demographics'),
            ('PHARMACY_STAFF','patients.view_demographics'),
            ('OWNER','patients.view_demographics')
          )
        )
        """
    )
    op.execute("DROP TABLE IF EXISTS patients")
