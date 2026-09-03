"""Doctor Management module: doctor_profiles (the DoctorProfile extension
of a staff User), user_branch_assignments (branch scoping for staff —
intentionally generic, not doctor-specific: Staff Management reuses it
next), and staff_invites (the invite -> accept-credentials mechanism the
PRD §5 workflow describes for onboarding any staff member, also generic).
See PRD-ARCHITECTURE.md §4 module list item 7, §6 (entities), §5 (staff
invite workflow).

Also adds `users.first_name` / `users.last_name`: the original schema
design (migration 0001, mirroring docs/schema/clinic_erp_schema.sql) gave
`users` no name field at all, only email/phone — unnoticed until this
module needed to show/search a doctor by name. Nullable (existing
PATIENT-role rows and test fixtures created before this migration have
neither), enforced as required at the Pydantic layer for doctor creation
specifically, not at the DB level, since `users` is shared by every role
including OTP-only patient logins that may never set a name.

`staff_invites` (not in the original PRD §6 entity sketch, like
`otp_codes`/`user_sessions` before it) stores only a hashed token — the
plaintext is returned to the caller once (and echoed in the API response
outside `production`, the same placeholder-delivery pattern already used
for OTP codes) and never persisted.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN first_name text")
    op.execute("ALTER TABLE users ADD COLUMN last_name text")

    op.execute(
        """
        CREATE TABLE doctor_profiles (
          user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          specialization       text,
          registration_number  text,
          consultation_fee     numeric(10,2),
          working_hours        jsonb NOT NULL DEFAULT '{}'::jsonb,
          bio                  text,
          created_at           timestamptz NOT NULL DEFAULT now(),
          updated_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER trg_doctor_profiles_updated_at BEFORE UPDATE ON doctor_profiles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE doctor_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE doctor_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON doctor_profiles
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE user_branch_assignments (
          id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          branch_id  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (user_id, branch_id)
        )
        """
    )
    op.execute("ALTER TABLE user_branch_assignments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_branch_assignments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON user_branch_assignments
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE staff_invites (
          id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash  text NOT NULL UNIQUE,
          expires_at  timestamptz NOT NULL,
          accepted_at timestamptz,
          created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_staff_invites_user_pending ON staff_invites (user_id) WHERE accepted_at IS NULL")
    op.execute("ALTER TABLE staff_invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_invites FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON staff_invites
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staff_invites")
    op.execute("DROP TABLE IF EXISTS user_branch_assignments")
    op.execute("DROP TABLE IF EXISTS doctor_profiles")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_name")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS first_name")
