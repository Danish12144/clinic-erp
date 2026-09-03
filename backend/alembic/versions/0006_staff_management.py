"""Staff Management module: staff_profiles (the StaffProfile extension of
a non-doctor staff User — Receptionist, Nurse, Lab Staff, Pharmacy Staff,
Other Staff). See PRD-ARCHITECTURE.md §4 (module list item 8), §6
(entities).

No permission changes — `staff.manage` (seeded in migration 0001, Owner
only, "Invite/manage staff accounts and role assignments") already covers
this capability row exactly. No new users/staff_invites/
user_branch_assignments columns needed either: this module reuses the
invite/accept flow (migration 0005, relocated to the Auth module by this
same migration's Python changes — see app/modules/auth/models.py) and
branch-assignment table as-is.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE staff_profiles (
          user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          employee_code text,
          designation   text,
          joining_date  date,
          created_at    timestamptz NOT NULL DEFAULT now(),
          updated_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER trg_staff_profiles_updated_at BEFORE UPDATE ON staff_profiles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE staff_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON staff_profiles
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staff_profiles")
