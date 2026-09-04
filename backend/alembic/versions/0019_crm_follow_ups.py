"""CRM & Follow-ups — PRD-ARCHITECTURE.md §4 (module list items 29/30),
§5.6, §20 (CRM Architecture), §6. Deliberately scoped to the *clinical
follow-up* half of PRD §20's `FollowUp`/`CommunicationLog` design, per
this task's own 4-point spec — not the CRM/Lead-pipeline half. `leads` and
`notification_templates` are NOT built here:

- The master schema's `follow_ups` is generic over `patient_id` OR
  `lead_id` (`CHECK (patient_id IS NOT NULL OR lead_id IS NOT NULL)`,
  "assignable to staff... system-generated or manual"), because it's
  meant to serve both CRM outreach (a `Lead`, not yet a `Patient`) and
  clinical follow-up ("come back in 2 weeks"). This task's own spec asks
  for follow-ups "linked to patient_id, doctor_id, encounter_id, and
  clinic_id" — a purely clinical shape, `patient_id` required, no
  `lead_id` at all. Since no `leads` table exists yet (out of scope; a
  future module can add lead-linked follow-ups without touching this
  table), `follow_ups` here is built narrower than the master schema's
  sketch, by direct instruction — same "purpose-built over generic,
  because that's what was actually asked for" call as `medical_documents`
  over `documents` (migration 0016).
- `follow_up_status` is created here for the first time (no earlier
  migration touched CRM) as `('PENDING','SENT','CONFIRMED','CANCELLED',
  'OVERDUE')` rather than the master schema's own `('PENDING','DONE',
  'CANCELLED')` — by direct instruction. `OVERDUE` has no scheduler to
  transition rows into it (no background-job infrastructure exists in
  this backend at all yet, per PRD §10's own "final pick is an
  implementation-time decision, not blocking this document"), so it's
  computed **lazily**: `FollowUpService` sweeps any `PENDING`/`SENT` row
  whose `due_at` has passed to `OVERDUE` the moment it's read (search or
  get), not on a timer. This is a deliberate, documented tradeoff, not an
  incomplete feature — see that service's module docstring.
- `communication_logs` (PRD §20: "All outbound patient-facing messages...
  are recorded in CommunicationLog... regardless of trigger") is built
  here in its general master-schema shape (reusable by any future
  notification-triggering module, not Follow-ups-specific) *except*
  `template_id`, kept as a plain nullable UUID with no FK — there is no
  `notification_templates` table yet, same "column exists, FK deferred"
  pattern `prescription_items.medicine_id` used before Pharmacy existed.
  Creating a follow-up stub-inserts exactly one `communication_logs` row
  (`status='QUEUED'`, no real SMS/WhatsApp provider — task 3's own
  "stubbed" framing, same placeholder-delivery precedent as OTP/staff
  invites) — task 3's "Outbox / notification log entry stubbed for
  automated... reminder triggers," not a live send.

Permission-matrix deviation, by direct instruction (not a seed-vs-matrix
gap fix): the PRD §3 matrix gives Doctor "–" (no access at all) on "CRM,
leads, follow-ups" — the product owner explicitly asked for Doctor to be
able to schedule and see their own follow-ups ("from doctor desk or
reception," "Doctor is scoped to their own follow-up patients"). Rather
than a new permission code, `crm.manage` (already Owner/Receptionist,
unscoped, matching the matrix's "F" exactly) is also granted to Doctor —
row-scoped to `doctor_id = caller` at the service layer, the same shared-
permission-code-plus-service-scoping pattern Consultation/Prescription
already established, not the separate `.view_own` split Billing/Dashboard
used (Doctor's CRM capability here is read+write on their own rows, not a
strictly-weaker read-only tier).

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-04

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE follow_up_status AS ENUM ('PENDING','SENT','CONFIRMED','CANCELLED','OVERDUE')")
    op.execute("CREATE TYPE comm_channel AS ENUM ('WHATSAPP','SMS','EMAIL','PUSH')")
    op.execute("CREATE TYPE comm_status AS ENUM ('QUEUED','SENT','DELIVERED','FAILED')")

    op.execute(
        """
        CREATE TABLE communication_logs (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          patient_id           UUID REFERENCES patients(id),
          lead_id              UUID,
          channel              comm_channel NOT NULL,
          template_id          UUID,
          status               comm_status NOT NULL DEFAULT 'QUEUED',
          provider_message_id  text,
          consent_basis        text,
          sent_at              timestamptz,
          created_at           timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_communication_logs_patient ON communication_logs (tenant_id, patient_id, created_at)")
    op.execute("ALTER TABLE communication_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE communication_logs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON communication_logs
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    op.execute(
        """
        CREATE TABLE follow_ups (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
          patient_id       UUID NOT NULL REFERENCES patients(id),
          doctor_id        UUID REFERENCES users(id),
          encounter_id     UUID REFERENCES encounters(id),
          due_at           timestamptz NOT NULL,
          status           follow_up_status NOT NULL DEFAULT 'PENDING',
          reason           text,
          reminder_log_id  UUID REFERENCES communication_logs(id),
          created_by       UUID NOT NULL REFERENCES users(id),
          created_at       timestamptz NOT NULL DEFAULT now(),
          updated_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_follow_ups_patient ON follow_ups (tenant_id, patient_id, due_at)")
    op.execute("CREATE INDEX ix_follow_ups_doctor ON follow_ups (doctor_id)")
    op.execute("CREATE INDEX ix_follow_ups_due_status ON follow_ups (tenant_id, status, due_at)")
    op.execute("CREATE TRIGGER trg_follow_ups_updated_at BEFORE UPDATE ON follow_ups FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    op.execute("ALTER TABLE follow_ups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE follow_ups FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON follow_ups
          USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
          WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())
        """
    )

    # --- Permission matrix deviation (Doctor read+write, own rows) -------
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('DOCTOR', 'crm.manage')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE (role_id, permission_id) IN (
          SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) = ('DOCTOR', 'crm.manage')
        )
        """
    )
    op.execute("DROP TABLE IF EXISTS follow_ups")
    op.execute("DROP TABLE IF EXISTS communication_logs")
    op.execute("DROP TYPE IF EXISTS comm_status")
    op.execute("DROP TYPE IF EXISTS comm_channel")
    op.execute("DROP TYPE IF EXISTS follow_up_status")
