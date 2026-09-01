# Clinic ERP + CRM — Database Schema Overview

**Status:** implemented and migrated so far — Auth module (`backend/app/modules/auth`, migrations `0001`, `0002`): `clinics`, `roles`, `permissions`, `role_permissions`, `users`, `permission_overrides`, `otp_codes`, `user_sessions`, plus the `app_user` DB role and its grants. Tenancy module (`backend/app/modules/tenancy`, migration `0003`): `branches`, `tenant_settings` (`clinics` itself was already covered by Auth — Tenancy just adds update capability and owns the model file now). Everything else here is still design-only, not yet applied to any database. Companion to [`PRD-ARCHITECTURE.md`](./PRD-ARCHITECTURE.md) and the full DDL at [`schema/clinic_erp_schema.sql`](./schema/clinic_erp_schema.sql). Read the SQL file for column-level detail; this doc explains the shape and the handful of decisions made while turning the PRD's entity sketch (§6) into real DDL.

**Tenancy module scope note:** `subscriptions` is deliberately not built yet — PRD §30's pricing-model question is still open, and building the table now would mean guessing at columns that will need to change once billing is actually designed. Clinic *creation* (tenant onboarding) is also out of scope for the Tenancy module as built — it's a Platform Admin operation, and no Platform Admin authentication exists yet (see `platform_admins` in the master schema, still unimplemented). The Tenancy module only manages settings/branches for a clinic that already exists (created today via direct DB access in tests, same as the Auth module's fixtures).

**Changelog:** `otp_codes` and `user_sessions` (Identity & RBAC section) were added while implementing the Auth module — not in the original PRD §6 entity sketch. Patient login (PRD §12) needs somewhere to hold a hashed, expiring OTP code, and refresh-token revocation (PRD §12's "opaque, stored server-side... allows revocation") needs somewhere to hold a hashed refresh token per device/session. Both follow the existing event-table convention (created_at only, RLS-scoped, no update trigger).

## How it's organized

The SQL file is one linear script, ordered so every `REFERENCES` points at a table already created above it (two exceptions noted inline, fixed up with `ALTER TABLE ... ADD CONSTRAINT` after the fact, to avoid reshuffling the whole file for two forward references). Sections mirror the PRD's domain grouping: tenancy → identity/RBAC → patients/encounters → pharmacy → prescriptions → laboratory → financial → inventory → CRM/communication → audit/documents → reserved-for-later.

## Decisions made while going from PRD sketch to DDL

**Roles and permissions are global, not tenant-scoped.** The PRD's §6 entity sketch mentioned "clinic-scoped custom roles for Other Staff variants" as a maybe. In the actual schema, `roles` and `permissions` are fixed, global reference data (the 8 roles from PRD §2, seeded in the SQL file), and **all** per-clinic customization — including anything an "Other Staff" role might need — goes through `permission_overrides`, which can target either a role or an individual user within one tenant. This is a direct implementation of the two-layer resolution PRD §13 already specified (`role_permissions` defaults → `permission_overrides` deltas); adding tenant-scoped custom roles on top would be a second customization mechanism doing overlapping work. If a clinic genuinely needs a role that doesn't map to any of the 8 (not just a permission tweak), that's a real gap in this design — worth raising if it comes up before implementation.

**Polymorphic references instead of FKs, in five places.** `invoice_line_items.source_type/source_id`, `documents.owner_type/owner_id`, `audit_logs.entity_type/entity_id`, `pharmacy_inventory_transactions.reference_type/reference_id`, and (temporarily, until the `ALTER TABLE` fix-up) `pharmacy_sales.invoice_id` all point at "one of several possible tables" and can't be a single real foreign key. Postgres has no native polymorphic FK — these are enforced in the application layer, not the database. This is a real gap the app's service layer must own: nothing stops a bad `owner_type` value or a dangling `owner_id` at the DB level.

**Two tables are genuinely DB-enforced append-only beyond `vitals`.** The product requirement to never overwrite a vitals reading (PRD §5.3) is implemented as a `BEFORE UPDATE OR DELETE` trigger that raises an exception — not just an app-layer convention. The same trigger is applied to `prescriptions` (immutable-with-supersession, PRD §5.7) and `audit_logs` (has to be tamper-evident to mean anything, PRD §14). Other event-like tables (`payments`, `pharmacy_inventory_transactions`, `communication_logs`) are *modeled* as insert-mostly but not DB-locked — a correction there is a new row with a reason, by convention, not by constraint. Worth revisiting if a compliance review calls for hard DB enforcement on payments too.

**Row-Level Security is real, not decorative.** Every tenant-owned table has `FORCE ROW LEVEL SECURITY` set, which matters: without `FORCE`, a table's owning role bypasses RLS entirely, and if the application connects as that owning role (common default), RLS silently does nothing. The policies read two session settings the app must set at the start of every request/transaction:

```sql
SET LOCAL app.current_tenant_id = '<tenant-uuid-from-jwt>';
-- only ever set by the Platform Admin service path:
SET LOCAL app.is_platform_admin = 'true';
```

**Recommended (not yet built) DB role setup:** a dedicated `app_user` Postgres role, *not* the table owner, used for all normal request-handling connections — so `FORCE ROW LEVEL SECURITY` actually bites. A separate, more privileged role (or the same role with `app.is_platform_admin` set only from the specific service path that's allowed to use it) for the Platform Admin bypass. Neither role should have `DROP`/`TRUNCATE`, and no role used by application code should have `UPDATE`/`DELETE` on `audit_logs` (belt-and-suspenders alongside the trigger). This is a deployment/ops task for implementation time, not something the DDL alone can guarantee.

**Vitals role is a snapshot, not a live FK.** `vitals.recorded_by_role` stores the role *code as text* at the moment of recording, rather than an FK to `roles`. A role's permissions can change over time (via `permission_overrides`); the historical record of "who recorded this, acting in what capacity, at that moment" should reflect that moment, not whatever the user's role happens to be today. `audit_logs.actor_role` follows the same pattern for the same reason.

**BMI is a generated column.** `vitals.bmi` is `GENERATED ALWAYS AS (...) STORED` from `weight_kg`/`height_cm`, null-safe. One less place for the frontend or backend to get the formula wrong or drift out of sync.

## What's still open

Everything flagged as an open question in [`PRD-ARCHITECTURE.md` §30](./PRD-ARCHITECTURE.md#30-risks-and-architectural-decisions) still applies here — most concretely:
- **Branch model** (assumed: one tenant, many branches) shapes `patients`/`appointments`/`invoices` being branch- vs. tenant-scoped the way they are now. If that assumption is wrong, this schema needs real rework, not a tweak.
- **Subscription/billing model** — `plans`/`subscriptions` are placeholders (seeded with two made-up example plans) pending a real pricing decision.
- **Multi-clinic staff membership** — `users.tenant_id` is `NOT NULL` and singular; a staff member working at two unrelated clinics needs two separate `users` rows today, not one account with two memberships.

## Applying this later

When implementation starts, this raw SQL is meant to become the *first* Alembic migration (`alembic revision --autogenerate` won't produce it as-is since SQLAlchemy models don't exist yet — more likely this becomes a hand-written initial migration, with SQLAlchemy models then written to match it, or the reverse — either way is a legitimate implementation-time call, not decided here). Nothing in this file has been executed against a real Postgres instance yet; treat it as reviewed-but-untested until a first migration run confirms it.
