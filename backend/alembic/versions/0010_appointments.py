"""Appointments module (booking only — online + receptionist booking;
walk-in/check-in/queue/vitals/EMR/consultation/e-prescription are later,
separate modules by explicit scope decision). Verbatim subset of
docs/schema/clinic_erp_schema.sql's `appointments` table and its two
enums. See PRD-ARCHITECTURE.md §4 module list items 10/11, §5.1 (steps
1-2), §6 (entities).

Also fixes a real permission-matrix gap in migration 0001's seed data,
the same kind two earlier modules already found: Doctor was granted
`appointments.manage` (full create/reschedule/cancel for any patient),
but the PRD §3 matrix gives Doctor only "R (own)" for this capability —
read access to their own schedule, not write access to anyone's. Fixed
here (never by editing an already-applied migration) by revoking that
grant and adding a new `appointments.view` permission (read-only, further
row-scoped to "own" for Doctor at the repository layer — same pattern as
`patients.view_emr`'s Doctor scoping) to Doctor, Nurse, and — since Owner/
Receptionist also need to *read* appointments, not just write them —
Owner and Receptionist too.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE appointment_source AS ENUM ('ONLINE','RECEPTIONIST','WALK_IN')")
    op.execute("CREATE TYPE appointment_status AS ENUM ('SCHEDULED','CHECKED_IN','IN_PROGRESS','COMPLETED','CANCELLED','NO_SHOW')")

    op.execute(
        """
        CREATE TABLE appointments (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          branch_id        UUID NOT NULL REFERENCES branches(id),
          patient_id       UUID NOT NULL REFERENCES patients(id),
          doctor_id        UUID REFERENCES users(id),
          source           appointment_source NOT NULL,
          scheduled_at     timestamptz NOT NULL,
          duration_minutes int NOT NULL DEFAULT 15,
          status           appointment_status NOT NULL DEFAULT 'SCHEDULED',
          notes            text,
          cancelled_reason text,
          cancelled_by     UUID REFERENCES users(id),
          cancelled_at     timestamptz,
          created_at       timestamptz NOT NULL DEFAULT now(),
          updated_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_appt_branch_time ON appointments (branch_id, scheduled_at)")
    op.execute("CREATE INDEX ix_appt_doctor_time ON appointments (doctor_id, scheduled_at)")
    op.execute("CREATE INDEX ix_appt_patient ON appointments (patient_id)")

    op.execute(
        "CREATE TRIGGER trg_appointments_updated_at BEFORE UPDATE ON appointments "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE appointments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE appointments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON appointments
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix correction + new read permission ------------------
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE (role_id, permission_id) IN (
          SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('DOCTOR', 'appointments.manage')
        )
        """
    )
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('appointments.view', 'appointments', 'View appointments — Doctor is further scoped to their own schedule')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','appointments.view'),
          ('DOCTOR','appointments.view'),
          ('RECEPTIONIST','appointments.view'),
          ('NURSE','appointments.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'appointments.view')
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'appointments.view'")
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('DOCTOR', 'appointments.manage')
        """
    )
    op.execute("DROP TABLE IF EXISTS appointments")
    op.execute("DROP TYPE IF EXISTS appointment_status")
    op.execute("DROP TYPE IF EXISTS appointment_source")
