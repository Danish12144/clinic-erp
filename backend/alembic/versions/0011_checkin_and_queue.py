"""Walk-in registration, check-in, and queue/token issuance —
PRD-ARCHITECTURE.md §4 module list items 12/13/14, §5.1 (steps 3/5/6), §6
(entities). Verbatim subset of docs/schema/clinic_erp_schema.sql's
`encounters`/`queue_tokens` tables and their two enums.

Bundled into one module/migration by explicit product-owner decision when
asked: queue/token issuance ships together with check-in rather than being
deferred to its own module (unlike how Appointments deferred check-in
itself to this module). `Encounter` is the hub entity for one clinic visit
(PRD §7) that vitals/consultation/prescriptions/lab/billing will key off in
later modules; `QueueToken` is issued 1:1 with an Encounter at check-in
time.

Also fixes a real permission-matrix gap, same kind found in every module
so far: migration 0001 granted NURSE the full `queue.manage` permission,
but the PRD §3 matrix gives Nurse only "R" for both "Walk-in registration &
check-in" and "Queue / token management" — read, not write. Fixed here by
revoking that grant and adding `checkin.view`/`queue.view` (read-only,
tenant/branch-wide — the matrix does not mark these rows "(own)" the way
it does Doctor's appointment-booking row, so unlike Appointments there is
no per-doctor row-scoping here) granted to Owner, Doctor, Receptionist, and
Nurse. Owner/Receptionist additionally keep `checkin.manage`/`queue.manage`
(already correct in migration 0001) for the write side.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE encounter_status AS ENUM ('OPEN','IN_CONSULTATION','COMPLETED','CANCELLED')")
    op.execute("CREATE TYPE queue_token_status AS ENUM ('WAITING','CALLED','IN_PROGRESS','DONE','NO_SHOW','SKIPPED')")

    op.execute(
        """
        CREATE TABLE encounters (
          id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          branch_id      UUID NOT NULL REFERENCES branches(id),
          appointment_id UUID REFERENCES appointments(id),
          patient_id     UUID NOT NULL REFERENCES patients(id),
          status         encounter_status NOT NULL DEFAULT 'OPEN',
          checked_in_at  timestamptz NOT NULL DEFAULT now(),
          completed_at   timestamptz,
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_encounter_appointment ON encounters (appointment_id) WHERE appointment_id IS NOT NULL")
    op.execute("CREATE INDEX ix_encounters_patient ON encounters (patient_id)")
    op.execute("CREATE INDEX ix_encounters_branch_date ON encounters (branch_id, checked_in_at)")
    op.execute(
        "CREATE TRIGGER trg_encounters_updated_at BEFORE UPDATE ON encounters "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE encounters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE encounters FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON encounters
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE queue_tokens (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id    UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          branch_id    UUID NOT NULL REFERENCES branches(id),
          encounter_id UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
          doctor_id    UUID REFERENCES users(id),
          token_date   date NOT NULL DEFAULT current_date,
          token_number int NOT NULL,
          status       queue_token_status NOT NULL DEFAULT 'WAITING',
          called_at    timestamptz,
          created_at   timestamptz NOT NULL DEFAULT now(),
          updated_at   timestamptz NOT NULL DEFAULT now(),
          UNIQUE (branch_id, token_date, token_number)
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_queue_encounter ON queue_tokens (encounter_id)")
    op.execute("CREATE INDEX ix_queue_branch_date_status ON queue_tokens (branch_id, token_date, status)")
    op.execute(
        "CREATE TRIGGER trg_queue_tokens_updated_at BEFORE UPDATE ON queue_tokens "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE queue_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE queue_tokens FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON queue_tokens
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix correction + new read permissions -----------------
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE (role_id, permission_id) IN (
          SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('NURSE', 'queue.manage')
        )
        """
    )
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('checkin.view', 'queue', 'View walk-ins/check-ins/encounters — tenant/branch-wide, not row-scoped'),
          ('queue.view',   'queue', 'View the queue/token board — tenant/branch-wide, not row-scoped')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','checkin.view'), ('OWNER','queue.view'),
          ('DOCTOR','checkin.view'), ('DOCTOR','queue.view'),
          ('RECEPTIONIST','checkin.view'), ('RECEPTIONIST','queue.view'),
          ('NURSE','checkin.view'), ('NURSE','queue.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('checkin.view', 'queue.view'))
        """
    )
    op.execute("DELETE FROM permissions WHERE code IN ('checkin.view', 'queue.view')")
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('NURSE', 'queue.manage')
        """
    )
    op.execute("DROP TABLE IF EXISTS queue_tokens")
    op.execute("DROP TABLE IF EXISTS encounters")
    op.execute("DROP TYPE IF EXISTS queue_token_status")
    op.execute("DROP TYPE IF EXISTS encounter_status")
