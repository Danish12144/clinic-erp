"""Fix a real conflict between two migration-0001 mechanisms that had
never been exercised together until this migration's predecessor added
the first append-only table (`audit_logs`, migration 0007): `clinics`
cascades `ON DELETE` to every tenant-owned table, including `audit_logs`
(`tenant_id ... REFERENCES clinics(id) ON DELETE CASCADE`, per the master
schema) — but `prevent_update_delete()` (migration 0001) unconditionally
raises on *any* DELETE against an append-only table, cascade-originated or
not, since a `BEFORE DELETE` trigger fires the same way either way.

In production this was never reachable (no code path deletes a `clinics`
row — clinic creation/deletion is a deferred Platform Admin concern), but
it broke every test whose teardown hard-deletes its throwaway clinic once
that clinic had any audit-logged activity: the cascade into `audit_logs`
hit the trigger and the whole teardown transaction failed.

Fix: `prevent_update_delete()` now allows the operation through when
`app_is_platform_admin()` is true — the same narrow, already-documented
RLS-bypass flag `app/core/db.py::platform_admin_session()` sets, used
today only for pre-auth tenant resolution and exactly this kind of test
cleanup. Normal application code always runs under `tenant_session`
(`is_platform_admin = false`) and is still unconditionally blocked, so the
actual guarantee this trigger exists for — no *application* code path can
tamper with append-only history — is unchanged; only the sanctioned
administrative bypass can now also remove these rows, e.g. as a side
effect of deleting the tenant that owns them entirely.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_update_delete() RETURNS trigger AS $$
        BEGIN
          IF app_is_platform_admin() THEN
            RETURN COALESCE(NEW, OLD);
          END IF;
          RAISE EXCEPTION 'rows in % are append-only and cannot be % (attempted on id=%)',
            TG_TABLE_NAME, TG_OP, COALESCE(OLD.id::text, 'unknown');
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_update_delete() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'rows in % are append-only and cannot be % (attempted on id=%)',
            TG_TABLE_NAME, TG_OP, COALESCE(OLD.id::text, 'unknown');
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
