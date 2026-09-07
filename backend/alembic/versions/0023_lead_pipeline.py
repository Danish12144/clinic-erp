"""Lead Pipeline / CRM Funnel — PRD-ARCHITECTURE.md §4 (module list item
28), §20, §6. Builds `leads`, design-only in `docs/schema/clinic_erp_schema.sql`
§12 since the file's original draft (the CRM & Follow-ups module, migration
0019, deliberately built only the clinical-follow-up half of PRD §20 and
left `leads` unbuilt — see that migration's own docstring), plus a wholly
new `lead_interactions` table this task asked for that the master schema
never sketched at all.

Deliberate deviations from the master schema's `leads` sketch, all by
direct instruction (this task's own field list):

1. `source` becomes a real `lead_source` enum
   (GOOGLE_AD/WALK_IN/WEBSITE/REFERRAL/SOCIAL) rather than the sketch's
   free text — same "fixed set, not open text" call as Expenses'
   `category`.
2. `status` is a wholly new `lead_status` enum (NEW/CONTACTED/
   APPOINTMENT_SCHEDULED/CONVERTED/LOST) — **not** a reuse of the master
   schema's already-sketched `lead_stage` enum (NEW/CONTACTED/QUALIFIED/
   CONVERTED/LOST), since `APPOINTMENT_SCHEDULED` replaces `QUALIFIED` in
   this task's own vocabulary and the two enums' value sets differ. This
   is possible without any `ALTER TYPE` gymnastics because `lead_stage`
   was itself only ever a doc-only sketch — no earlier migration ever
   actually created it (`leads` has never been migrated until now), so
   there's no live type to rename or alter; `lead_status` is simply a
   fresh, differently-named type for a fresh column.
3. `name` (a single free-text column in the sketch) becomes
   `first_name`/`last_name`, matching every other person-shaped entity in
   this schema (`patients`, `users`) rather than the sketch's single field.
4. Column is named `assigned_to_user_id`, not the sketch's `assigned_to` —
   this task's own literal field name.

`lead_interactions` (transaction_id/lead_id/clinic_id/interaction_type/
outcome/notes/performed_by, per this task's own field list — `clinic_id`
maps to this schema's `tenant_id`, `transaction_id` to `id`, same
terminology mapping every other module uses) is a pure outreach-activity
log — no `communication_logs` reuse, since that table's job (PRD §20) is
outbound message *delivery* tracking (channel/status/provider_message_id),
not a free-form "what happened on this call" note; a lead interaction may
not even be an outbound send (e.g. `NOTE`). `created_at` only, no
`updated_at` — same "insert-only, no update method" convention as
`payments`/`pharmacy_inventory_transactions`/`communication_logs`.

**RBAC is a direct product-owner deviation from the PRD §3 matrix, not a
gap-fix, and deliberately does NOT reuse the existing `crm.manage`
permission** (Owner/Receptionist/Doctor-for-their-own-follow-ups since
migration 0019) despite the matrix modeling "CRM, leads, follow-ups" as
one combined row. Reusing `crm.manage` for Leads would have silently
handed Doctor *write* access to leads too, since Doctor already holds that
code for follow-ups — this task explicitly wants Doctor read-only on
leads, a different tier than their follow-ups access. Two new,
leads-specific permissions instead: `leads.manage` (Owner/Receptionist,
full CRUD + convert) and `leads.view` (Doctor, read-only). Nurse/Lab
Staff/Pharmacy Staff/Other Staff/Patient get neither — zero access,
matching the matrix's "–" (Other Staff's matrix "C" was never asked for
here, unlike General Inventory's task explicitly naming "Staff").

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-07

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE lead_source AS ENUM ('GOOGLE_AD','WALK_IN','WEBSITE','REFERRAL','SOCIAL')")
    op.execute("CREATE TYPE lead_status AS ENUM ('NEW','CONTACTED','APPOINTMENT_SCHEDULED','CONVERTED','LOST')")
    op.execute("CREATE TYPE lead_interaction_type AS ENUM ('CALL','WHATSAPP','NOTE','EMAIL')")

    op.execute(
        """
        CREATE TABLE leads (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          first_name           text NOT NULL,
          last_name            text,
          phone                text,
          email                text,
          source               lead_source,
          status               lead_status NOT NULL DEFAULT 'NEW',
          assigned_to_user_id  UUID REFERENCES users(id),
          notes                text,
          converted_patient_id UUID REFERENCES patients(id),
          created_at           timestamptz NOT NULL DEFAULT now(),
          updated_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_leads_status ON leads (tenant_id, status)")
    op.execute("CREATE INDEX ix_leads_assigned ON leads (tenant_id, assigned_to_user_id)")
    op.execute("CREATE INDEX ix_leads_created ON leads (tenant_id, created_at)")
    op.execute("CREATE TRIGGER trg_leads_updated_at BEFORE UPDATE ON leads FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE leads ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leads FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON leads
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE lead_interactions (
          id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          lead_id           UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
          interaction_type  lead_interaction_type NOT NULL,
          outcome           text,
          notes             text,
          performed_by      UUID NOT NULL REFERENCES users(id),
          created_at        timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_lead_interactions_lead ON lead_interactions (lead_id, created_at)")
    op.execute("ALTER TABLE lead_interactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE lead_interactions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON lead_interactions
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (leads split out from crm.manage; Doctor read-only) ---
    op.execute(
        """
        INSERT INTO permissions (code, module, description) VALUES
          ('leads.manage', 'crm', 'Full CRUD on leads, log interactions, and convert a lead to a patient — Owner/Receptionist'),
          ('leads.view', 'crm', 'Read-only access to leads and their interaction history — Doctor')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
          ('OWNER','leads.manage'),
          ('RECEPTIONIST','leads.manage'),
          ('DOCTOR','leads.view')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ('leads.manage', 'leads.view'))
        """
    )
    op.execute("DELETE FROM permissions WHERE code IN ('leads.manage', 'leads.view')")
    op.execute("DROP TABLE IF EXISTS lead_interactions")
    op.execute("DROP TABLE IF EXISTS leads")
    op.execute("DROP TYPE IF EXISTS lead_interaction_type")
    op.execute("DROP TYPE IF EXISTS lead_status")
    op.execute("DROP TYPE IF EXISTS lead_source")
