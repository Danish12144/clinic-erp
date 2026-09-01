"""Create the non-superuser `app_user` Postgres role the running app
connects as, and grant it exactly what it needs.

This is the missing piece that makes Row-Level Security (migration 0001,
docs/schema/clinic_erp_schema.sql §16) actually bite: Postgres superusers
—  and table owners, unless FORCE ROW LEVEL SECURITY is set — always
bypass RLS. Migrations run as the superuser (needs CREATE TABLE/ROLE/
POLICY privileges); the running application must NOT, or every RLS policy
in the system is a no-op. See docs/DATABASE-SCHEMA.md's "Row-Level
Security is real, not decorative" section, which flagged this as a
deployment task — now implemented.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Only used to create the role the first time; not re-applied on later
# runs. Change it (ALTER ROLE app_user WITH PASSWORD '...') for any
# environment beyond local dev, and set DATABASE_URL to match — never
# commit a real password here.
_DEV_DEFAULT_PASSWORD = "app_user_dev_password_change_me"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
            CREATE ROLE app_user LOGIN PASSWORD '{_DEV_DEFAULT_PASSWORD}';
          END IF;
        END
        $$;
        """
    )

    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO app_user")
    # So tables added by future migrations are automatically granted too,
    # without a new grants migration every time.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO app_user")

    # No append-only table (audit_logs, vitals, prescriptions — PRD §14,
    # §25) exists yet in this migration's scope; each of those tables'
    # own future migration should add
    # `REVOKE UPDATE, DELETE ON <table> FROM app_user` at creation time,
    # as defense-in-depth alongside its prevent_update_delete() trigger —
    # don't rely on remembering to come back and add it here later.


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM app_user")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM app_user")
    op.execute("REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public FROM app_user")
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_user")
    op.execute("DROP ROLE IF EXISTS app_user")
