"""Vitals: `vitals`, verbatim from docs/schema/clinic_erp_schema.sql
(PRD-ARCHITECTURE.md §4 module list item 15, §5.1, §6). Append-only at the
DB level, same `prevent_update_delete()` mechanism reserved since migration
0001 and first used by `audit_logs` (migration 0007) — "never overwrite a
reading, a new one is always a new row" (PRD §5.3). `bmi` is a generated
column so callers never (mis)calculate it themselves.

Permission matrix correction/addition: migration 0001 already seeded
`vitals.record` correctly per the PRD §3 matrix's "Vitals recording" row
(Owner F, Doctor C-default-on, Receptionist C-default-off, Nurse
C-default-on) — Owner/Doctor/Nurse have it, Receptionist does not, and
that's unchanged here. What was missing is a *read* permission: the matrix
has no separate "view vitals" row (only "recording"), but front-desk
coordination needs Receptionist to at least see whether vitals were taken,
and Doctor/Nurse plainly need to see readings they didn't personally
record. `vitals.view` is added and granted to Owner, Doctor, Receptionist,
and Nurse — not Patient (the matrix's "Vitals recording" row gives Patient
"–", unlike the broader "Full patient EMR" row's Patient "O (read)"; a
patient's own-vitals visibility is presumed to arrive with the not-yet-
built EMR module, not this narrower recording-focused one). Not row-scoped
to "own" for Doctor: same reasoning as Check-in (migration 0011) — the
matrix doesn't mark this row "(own)" the way it does Doctor's appointment-
booking row.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE vitals (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          encounter_id         UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
          patient_id           UUID NOT NULL REFERENCES patients(id),
          recorded_by          UUID NOT NULL REFERENCES users(id),
          recorded_by_role     text NOT NULL,
          recorded_at          timestamptz NOT NULL DEFAULT now(),
          systolic_bp          int,
          diastolic_bp         int,
          heart_rate           int,
          temperature_celsius  numeric(4,1),
          spo2                 int,
          weight_kg            numeric(5,2),
          height_cm            numeric(5,2),
          bmi                  numeric(5,2) GENERATED ALWAYS AS (
            CASE WHEN weight_kg IS NOT NULL AND height_cm IS NOT NULL AND height_cm > 0
              THEN ROUND((weight_kg / ((height_cm / 100.0) ^ 2))::numeric, 2)
              ELSE NULL END
          ) STORED,
          notes      text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_vitals_encounter ON vitals (encounter_id, recorded_at)")
    op.execute("CREATE INDEX ix_vitals_patient ON vitals (patient_id, recorded_at)")

    op.execute(
        "CREATE TRIGGER trg_vitals_immutable BEFORE UPDATE OR DELETE ON vitals "
        "FOR EACH ROW EXECUTE FUNCTION prevent_update_delete()"
    )

    op.execute("ALTER TABLE vitals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE vitals FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON vitals
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute("REVOKE UPDATE, DELETE ON vitals FROM app_user")

    # --- New read permission ---------------------------------------------
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('vitals.view', 'vitals', 'View recorded vitals readings — tenant-wide, not row-scoped')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','vitals.view'),
          ('DOCTOR','vitals.view'),
          ('RECEPTIONIST','vitals.view'),
          ('NURSE','vitals.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'vitals.view')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'vitals.view'")
    op.execute("DROP TABLE IF EXISTS vitals")
