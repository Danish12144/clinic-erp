"""Notification Templates & Outbox Integration — PRD-ARCHITECTURE.md §4
(module list item 31), §20, §6. Builds `notification_templates`,
design-only in `docs/schema/clinic_erp_schema.sql` §12 since the file's
original draft (the CRM & Follow-ups module, migration 0019, deliberately
left it unbuilt — "nothing has needed templated content, only the plain
stub `communication_logs` row Follow-ups already creates"). Also finally
fulfills two promises earlier migrations made once this table exists:

1. `communication_logs.template_id` gets its deferred `REFERENCES
   notification_templates(id)` FK via `ALTER TABLE` (created without one in
   migration 0019 since the target table didn't exist yet — same "column
   reserved, FK deferred" pattern `prescription_items.medicine_id` used
   before Pharmacy shipped).
2. `communication_logs` gains a new `rendered_body` column (nullable text)
   — a genuine sketch gap, same category as `users.first_name`/
   prescription `route`: without it, there was no way for anyone (a
   `GET /api/v1/notifications/logs` caller, or this migration's own
   `send-preview` endpoint) to see *what message text* was actually
   queued/rendered, only that some message existed. Rows written before
   this migration (Follow-ups' pre-existing stub-only inserts) simply have
   `rendered_body = NULL`.

Deliberate choices, by direct instruction (this task's own field list):

1. `channel` reuses the existing `comm_channel` enum (WHATSAPP/SMS/EMAIL/
   PUSH, migration 0019) rather than a new one — this task's requested
   set (SMS/WHATSAPP/EMAIL) is a pure subset, and it's the exact same
   "which channel was this communication over" concept `communication_logs.
   channel` already uses; no reason to fork a second type for it. `PUSH`
   stays reachable on a template even though nothing dispatches over it
   yet, same as `communication_logs` itself already tolerated an unused
   enum member.
2. `template_key` stays free text, NOT a fixed enum — this task's own
   wording ("e.g. APPOINTMENT_BOOKED, ...") signals a non-exhaustive,
   extensible set, matching the master schema's own `event_key text`
   design intent (comment: "e.g. 'appointment.booked', 'lab_result.ready'"
   — this task's own casing style, `UPPER_SNAKE_CASE`, is used instead of
   dot-separated, but the "open string, not a closed enum" design is kept).
3. `variables` is `jsonb`, not the master schema's plain array-of-text
   design (never actually specified there) — this task's own wording is
   literally "JSON array of placeholders," and JSONB matches
   `lab_test_catalog.reference_ranges`'s own "structured JSON, still data
   not code" precedent.
4. `UNIQUE (tenant_id, channel, template_key)` — one active-or-inactive
   template per clinic per channel per trigger key. A `POST` for a
   combination that already exists 409s rather than silently duplicating;
   "override" (task wording) means a clinic customizing the rendering for
   a trigger the system already fires by default, not multiple competing
   templates for the same trigger.

**RBAC is a direct product-owner deviation from the PRD §3 matrix, not a
gap-fix**: the matrix has no dedicated row for "notification templates" at
all (the closest, "Patient communication (send)," is Owner/Receptionist/
Other-Staff-configurable only). The product owner explicitly asked for
Receptionist AND Doctor to have read-only access to templates and logs,
alongside Owner's full customization — two new permissions:
`notifications.manage` (Owner, full CRUD + preview) and
`notifications.view` (Receptionist/Doctor, read-only).

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-08

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notification_templates (
          id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id    UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          template_key text NOT NULL,
          channel      comm_channel NOT NULL,
          body_text    text NOT NULL,
          variables    jsonb NOT NULL DEFAULT '[]'::jsonb,
          is_active    boolean NOT NULL DEFAULT true,
          created_at   timestamptz NOT NULL DEFAULT now(),
          updated_at   timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, channel, template_key)
        )
        """
    )
    op.execute("CREATE TRIGGER trg_notification_templates_updated_at BEFORE UPDATE ON notification_templates FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE notification_templates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_templates FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON notification_templates
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Fulfill migration 0019's deferred FK + fill a real sketch gap ----
    op.execute("ALTER TABLE communication_logs ADD COLUMN rendered_body text")
    op.execute(
        "ALTER TABLE communication_logs ADD CONSTRAINT fk_communication_logs_template FOREIGN KEY (template_id) REFERENCES notification_templates(id)"
    )

    # --- Permission matrix deviation (no dedicated matrix row for this) --
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('notifications.manage', 'communications', 'Full CRUD on notification templates, preview rendering, and log inspection — Owner'),
          ('notifications.view', 'communications', 'Read-only access to notification templates and dispatch logs — Receptionist/Doctor')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','notifications.manage'),
          ('RECEPTIONIST','notifications.view'),
          ('DOCTOR','notifications.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('notifications.manage', 'notifications.view'))
        """
    )
    op.execute("DELETE FROM permissions WHERE code IN ('notifications.manage', 'notifications.view')")
    op.execute("ALTER TABLE communication_logs DROP CONSTRAINT IF EXISTS fk_communication_logs_template")
    op.execute("ALTER TABLE communication_logs DROP COLUMN IF EXISTS rendered_body")
    op.execute("DROP TABLE IF EXISTS notification_templates")
