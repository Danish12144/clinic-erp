"""Audit Logging: `audit_logs`, verbatim from docs/schema/clinic_erp_schema.sql
section 14/15b/16b. See PRD-ARCHITECTURE.md §14 — this was called out in
PRD §29 as a Phase 0 (Foundation) deliverable but wasn't actually built
until now; retrofitted in before Appointments (Phase 2) rather than
before Phase 0, since nothing before this needed writing to it in a way
that mattered enough to block on.

Append-only at the DB level, same mechanism reserved since migration 0001
for `vitals`/`prescriptions` (`prevent_update_delete()`, still unused by
either of those — neither table exists yet). `entity_id` has no FK
(polymorphic — this table logs changes across every module's entities).

`app_user` is explicitly REVOKEd UPDATE/DELETE on this table, per the
note left in migration 0002 for exactly this situation — belt-and-
suspenders alongside the trigger, in case a future bug ever tries to
bypass the trigger via a different code path.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_logs (
          id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          actor_user_id UUID REFERENCES users(id),
          actor_role    text,
          action        text NOT NULL,
          entity_type   text NOT NULL,
          entity_id     UUID,
          before        jsonb,
          after         jsonb,
          ip_address    inet,
          user_agent    text,
          created_at    timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_entity ON audit_logs (tenant_id, entity_type, entity_id)")
    op.execute("CREATE INDEX ix_audit_actor ON audit_logs (tenant_id, actor_user_id, created_at)")

    op.execute(
        "CREATE TRIGGER trg_audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs "
        "FOR EACH ROW EXECUTE FUNCTION prevent_update_delete()"
    )

    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_logs
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
