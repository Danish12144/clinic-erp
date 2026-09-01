"""Tenancy module: branches and the generic tenant_settings bag. Verbatim
subset of docs/schema/clinic_erp_schema.sql section 4 — `clinics` and
`subscriptions` are out of scope here: `clinics` already exists (created in
migration 0001, needed by Auth), and `subscriptions` is deliberately
excluded (PRD-ARCHITECTURE.md §30 open question — pricing model
undecided).

No new grants needed: migration 0002's `ALTER DEFAULT PRIVILEGES` already
covers any table created afterwards by the same (superuser) migration
role, including these two.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE branches (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          name          text NOT NULL,
          address       text,
          phone         text,
          timezone      text,
          working_hours jsonb NOT NULL DEFAULT '{}'::jsonb,
          is_active     boolean NOT NULL DEFAULT true,
          created_at    timestamptz NOT NULL DEFAULT now(),
          updated_at    timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, name)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE tenant_settings (
          id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          key        text NOT NULL,
          value      jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, key)
        )
        """
    )

    for table in ("branches", "tenant_settings"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
              WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
            """
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_settings")
    op.execute("DROP TABLE IF EXISTS branches")
