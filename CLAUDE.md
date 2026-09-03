# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state — read this first

This repo pivoted from a single-tenant demo scaffold to **Clinic ERP + CRM**, a multi-tenant SaaS product, being built module-by-module against a from-scratch design. The authoritative design docs are:

- `docs/PRD-ARCHITECTURE.md` — full product requirements + technical architecture (30 sections: roles, permission matrix, modules, workflows, entities, API structure, multi-tenant/auth/RBAC strategy, deployment, phasing, open questions).
- `docs/DATABASE-SCHEMA.md` + `docs/schema/clinic_erp_schema.sql` — the complete hand-designed Postgres schema (all modules), with a narrative doc explaining the design decisions and its own changelog of what's since been added during implementation.

**Everything else describing "the system" predates this pivot and is superseded — do not trust it as current behavior:**
- `README.md`, `docs/architecture.md`, `docs/database-schema.md`, `docs/api-spec.md` describe the original single-tenant demo's intended design.
- `backend-legacy-node-scaffold/` is the original Node/Express/TypeScript backend, preserved (renamed, not deleted) when the new Python/FastAPI backend replaced it in `backend/`. Nothing in it is wired to anything current.
- `frontend/` still holds the original single-tenant React/Vite demo UI (a single `App.tsx` with hardcoded mock data). The new SaaS frontend has not been started — building it is explicitly out of scope until the backend is far enough along (per direct instruction from the project owner).

**Build order is strict and incremental, one module at a time**, following `docs/PRD-ARCHITECTURE.md` §10's module list — each module gets Models, Schemas, Repository, Service, Router, and Tests (unit + integration + tenant-isolation) before the next one starts. Do not start a new module without being asked to.

**Module status:**
| Module | Status |
|---|---|
| Auth (identity, RBAC, staff login, patient OTP login, sessions) | ✅ Done — `backend/app/modules/auth/`, migrations `0001`, `0002` |
| Tenancy (clinic settings, branches) | ✅ Done — `backend/app/modules/tenancy/`, migration `0003`. Clinic *creation*/onboarding and `subscriptions` are explicitly out of scope — see the module's own doc note in `docs/DATABASE-SCHEMA.md` |
| Patient Management (registration, search, demographics) | ✅ Done — `backend/app/modules/patients/`, migration `0004`. Merge-duplicate-patients and portal-account linking are explicitly out of scope — see the module's own doc note in `docs/DATABASE-SCHEMA.md` |
| Doctor Management (provisioning, profile, branch assignment) | ✅ Done — `backend/app/modules/doctors/`, migration `0005`. Now also exposes `GET /api/v1/doctors/directory` (migration `0008`, `doctors.view_directory`) — a read-only, PII-minimal listing for Receptionist/Patient booking flows; the Owner-only management view (`GET /api/v1/doctors`) is unchanged |
| Staff Management (non-doctor staff: Receptionist/Nurse/Lab/Pharmacy/Other) | ✅ Done — `backend/app/modules/staff/`, migration `0006`. No self-service "/me" (Owner-only capability per the PRD matrix) and no role-change-after-creation — see the module's own doc note in `docs/DATABASE-SCHEMA.md` |
| Audit Logging | ✅ Done — `backend/app/modules/audit/`, migration `0007` (table) + `0009` (fixed a real trigger/cascade bug — see architecture notes below). Retrofitted into Patients/Doctors/Staff's mutating endpoints; `GET /api/v1/audit-logs` is Owner-only (`audit.view`, already seeded in migration `0001`) |
| Everything else (appointments, EMR, pharmacy, lab, billing, CRM, ...) | Not started |

## Commands

Run from `backend/` unless noted. There is no root-level command runner — this is a from-scratch Python backend, unrelated to the old root `package.json`.

```bash
# One-time setup
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env   # edit if your local Postgres isn't on the default port

# Local Postgres for dev/tests (disposable; separate from infrastructure/docker-compose.yml,
# which is the *old* scaffold's stack and unrelated)
docker compose -f docker-compose.test.yml up -d

# Migrations
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic revision -m "description"   # new migration, write DDL by hand (see below)

# Run the API
.venv/Scripts/python.exe -m uvicorn app.main:app --reload

# Tests
.venv/Scripts/python.exe -m pytest                       # full suite
.venv/Scripts/python.exe -m pytest tests/unit             # no DB needed, always runs
.venv/Scripts/python.exe -m pytest tests/integration tests/tenant_isolation   # needs the DB above; auto-skip if unreachable
.venv/Scripts/python.exe -m pytest tests/unit/test_security.py::test_hash_password_roundtrip   # single test
```

**Port 5432 is occupied by a native Postgres service on this dev machine** (not Docker) — `docker-compose.test.yml` maps the test container to host port **5433**, and `.env.example`/`.env` point at 5433 accordingly. Don't "fix" this back to 5432 without checking what's actually listening there first (`netstat -ano | grep 5432`).

There is no linter configured yet.

## Architecture notes — things that aren't obvious from reading one file

**Migrations are hand-written raw SQL, not autogenerated**, and are a deliberate curated subset of `docs/schema/clinic_erp_schema.sql` — only what the modules built so far actually use (e.g. migration `0001` skips `doctor_profiles`/`staff_profiles`/`user_branch_assignments` even though they're in the master schema, because no module needs them yet). When adding a table for a new module, copy its DDL from the master schema file into a new migration rather than letting `alembic revision --autogenerate` invent something that might drift from the design doc. Keep both in sync — see `docs/DATABASE-SCHEMA.md`'s changelog note for the pattern (two tables, `otp_codes` and `user_sessions`, were discovered as needed *during* Auth implementation and added to the master schema doc after the fact — this is expected, not a process failure).

**Tenant isolation requires a non-superuser DB role — this is the single easiest thing to break.** `DATABASE_URL` (used by the running app) must point at `app_user` (created in migration `0002`), never at the `postgres` superuser used by `DATABASE_URL_SYNC` for migrations. Postgres superusers **always bypass Row-Level Security**, `FORCE ROW LEVEL SECURITY` notwithstanding — connecting the app as `postgres` silently defeats every tenant-isolation guarantee in the system with no error of any kind. This exact bug was caught by the `tests/tenant_isolation/` suite the first time the Auth module's tests ran (cross-tenant login and cross-tenant row reads both "worked" until the role was fixed) — if a future change to `app/core/db.py` or `.env` makes tenant isolation tests fail in a way that looks like RLS just isn't applying, check this first.

**`app/core/db.py` has two session context managers, not one**: `tenant_session(tenant_id)` for all normal authenticated request handling, and `platform_admin_session()` for the narrow, explicitly-justified cross-tenant bypass (currently used only to resolve a clinic slug to a tenant id pre-authentication, in `app/modules/auth/repository.py::TenantResolutionRepository`). Any new use of `platform_admin_session()` should be treated as a design decision worth a comment explaining why, not a convenience.

**RLS session variables use `set_config(..., true)`, not `SET LOCAL`.** `SET LOCAL x = :param` is not valid Postgres syntax with bind parameters (`SET` isn't a normal DML statement) — this broke on first real test run against a live DB (`syntax error at or near "$1"`). `SELECT set_config('app.current_tenant_id', :value, true)` is the parameterizable equivalent and is just as transaction-scoped.

**The async test suite uses `NullPool` when `ENVIRONMENT=test`** (`app/core/db.py`), not the default pooled engine. pytest-asyncio's function-scoped event loops don't mix with pooled asyncpg connections opened on a previous test's loop — surfaces on Windows as a confusing `AttributeError` / "Event loop is closed" during teardown. `tests/conftest.py` sets `ENVIRONMENT=test` by default; don't remove that without addressing the underlying loop-scoping issue differently.

**JWT access tokens carry the resolved permission set, not just a role.** `app/core/security.py::create_access_token` embeds the user's *effective* permissions (role defaults + `permission_overrides`, resolved once at login/refresh by `PermissionRepository.resolve_effective_permissions`) directly in the token payload. `app/api/deps.py::require_permission(...)` checks membership in that embedded list — zero DB hits on protected routes. A clinic owner revoking a permission takes effect for that user on their *next token refresh*, not instantly. This is what makes the "Owner turns on vitals-recording for Receptionists at their clinic" requirement (PRD §3/§13) work without per-request DB queries.

**Refresh tokens and OTP codes are opaque and stored only as SHA-256 hashes** (`user_sessions.refresh_token_hash`, `otp_codes.code_hash`) — never the raw value, so a DB read alone can't be used to impersonate a session or replay a login code. OTP delivery is a `ConsoleOtpSender` that just logs the code (`app/modules/auth/otp_sender.py`) — not production-safe, a placeholder until the Communications module ships a real WhatsApp/SMS adapter; `AuthService` also echoes the code back in the API response body whenever `ENVIRONMENT != production`, which is what lets integration tests complete the OTP flow with no external provider.

**`vitals`, `prescriptions`, and `audit_logs` are append-only at the database level**, not just by app convention — a `BEFORE UPDATE OR DELETE` trigger (`prevent_update_delete()`) raises on any attempt, per the explicit "never overwrite, preserve history" product requirement. None of these three tables exist yet (they belong to later modules); when they're created, follow the pattern already established for `otp_codes`/`user_sessions` and add the trigger in that same migration, plus a `REVOKE UPDATE, DELETE ... FROM app_user` (see the comment left for this in migration `0002`).

**New tables don't need their own grants migration.** Migration `0002`'s `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ... TO app_user` applies to any table a later migration creates (confirmed working in migration `0003` — `branches`/`tenant_settings` needed no explicit `GRANT`), as long as that migration runs under the same DB role (the `postgres` superuser via `DATABASE_URL_SYNC`) that ran `ALTER DEFAULT PRIVILEGES` in the first place. Don't add per-table `GRANT ... TO app_user` statements out of habit.

**Read-vs-write permission split isn't uniform across a module — check what the data actually is.** In Tenancy, branch reads are open to any authenticated staff (operational reference data everyone needs — scheduling, check-in) while clinic settings reads are Owner-only (`clinic.manage_settings`, administrative/config data). Don't assume "GET routes are always open" or "always permission-gated" when adding a new module's routes — decide per resource, the way `app/modules/tenancy/router.py` does, and say why in a comment.

**Reusable test fixtures now live centrally in `tests/conftest.py`, not per-module.** `login_as(role_code=...)` and `owner_headers` (built on it) were added while testing Tenancy specifically so future modules' integration tests don't re-implement "create a staff user with role X, log in via the real endpoint, return auth headers" each time — use them instead of hand-rolling login boilerplate in a new module's tests.

**Staff account provisioning is a real invite/accept-token flow, not an Owner-set password** — `staff_invites` (table created by migration `0005`) stores only a hashed opaque token; `POST /api/v1/doctors` or `POST /api/v1/staff` creates the `User` (status `INVITED`, no `password_hash`) and returns the raw token in the response body outside `production` only (`debug_invite_token`, same placeholder-delivery pattern as OTP's `debug_code` — no Communications module exists yet to deliver it by email/SMS for real). The invited person calls `POST /api/v1/auth/accept-invite` with `{clinic_slug, token, password}` to set their password and flip to `ACTIVE`, then logs in normally via `/api/v1/auth/staff/login`. A resend (`POST /api/v1/doctors/{user_id}/invite/resend` or the `/api/v1/staff/...` equivalent) deletes any still-pending invite row for that user first, so an old leaked/previous token stops working the moment a new one is issued.

The mechanism's Python home moved once it needed a second caller: migration `0005` (Doctor Management) built `StaffInvite`/its repository/`POST /api/v1/doctors/accept-invite` inside the `doctors` module; migration `0006` (Staff Management) relocated the model, repository, and endpoint into the **Auth** module (`app/modules/auth/{models,repository,schemas,service,router}.py`) — a pure code move, no table/column change — because activating an invited account is role-agnostic, and leaving it under `/doctors` would have meant a newly-invited nurse posting to a `/doctors/...` URL. `issue_staff_invite` (a free function in `app/modules/auth/service.py`, not an `AuthService` method — it's called from within Doctor/Staff Management's own already-open `tenant_session`, not a fresh one) is the shared issuance path both modules call. `UserBranchAssignment` stayed in the `doctors` module (as `BranchAssignmentRepository`, generically named) since branch scoping isn't a credentials concern — Staff Management imports it directly rather than duplicating it. If a third module ever needs either mechanism, this is the pattern to follow.

**`users.first_name`/`last_name` didn't exist until migration `0005`.** The original schema design (migration `0001`) gave `users` no display-name field at all, only `email`/`phone` — unnoticed until Doctor Management needed to show/search a doctor by name. Added as nullable columns (existing rows, and OTP-only patient users, may have neither) and enforced as required only at the Pydantic layer for doctor creation specifically. If a future module hits a `None` where a name was assumed, check whether that `User` row predates migration `0005` or was created via a path (like the `PATIENT` OTP flow) that still never sets one.

**Audit logging is a per-module `record()` call, not a generic hook.** `app/modules/audit/service.py::record` is a free function (same shape as `issue_staff_invite`) — every mutating service method that should be audited calls it directly, passing the already-open `session` from its own `tenant_session`, so the audit row commits atomically with the change it describes. It was retrofitted into Patients (create/update/soft-delete), Doctors, and Staff (create/update/deactivate/reactivate/branch-assignment) when the module was built (migration `0007`); Tenancy (clinic settings, branches) was deliberately left un-audited for now — lower-stakes admin config, not a PHI/access-control entity. **Any new mutating endpoint on an entity that's clinically, financially, or access-control relevant should call `record()` at the point of the change** (PRD §14) — don't wait to be asked; check this note before adding a create/update/delete on Patients/Doctors/Staff-like entities (Appointments, EMR, etc. all qualify).

**The append-only trigger (`prevent_update_delete()`) has an escape valve for `app_is_platform_admin()`, added in migration `0009`.** Building the *first* append-only table (`audit_logs`, migration `0007`) exposed a real bug dormant since migration `0001`: `clinics` cascades `ON DELETE` to every tenant table including `audit_logs`, but the trigger unconditionally blocked *any* delete, cascade or not — harmless in production (nothing deletes a `clinics` row today) but broke every test's teardown once its throwaway clinic had audit-logged activity. Fixed by letting the trigger check the same `app_is_platform_admin()` flag `platform_admin_session()` sets — application code under normal `tenant_session` is still unconditionally blocked; only the already-sanctioned administrative bypass can remove these rows. **When Vitals/Prescriptions (the other two tables this trigger is reserved for) get built, this is already handled** — don't re-solve it.

**Migration 0001's `role_permissions` seed data has had two rounds of gaps found and fixed by later modules' integration tests** (both in migration `0004`, both surfaced as unexpected 403s, not schema errors): Lab Staff/Pharmacy Staff missing `patients.view_demographics`, and Owner missing it despite having the broader `patients.view_emr`. **Treat a 403 you didn't expect in a new module's tests as a real signal to check the seed data against the PRD §3 matrix, not just a bug in the new module's router** — the matrix is the source of truth; migration 0001's seed is a first pass at it and has been wrong twice already. Fix gaps in the *current* module's migration (as `0004` did), never by editing an already-applied one.
