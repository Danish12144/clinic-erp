-- =============================================================================
-- Clinic ERP + CRM — PostgreSQL Schema Design
-- =============================================================================
-- Status: DESIGN ONLY. Not yet executed against any database, not yet wired
-- into an Alembic migration chain. Companion to ../PRD-ARCHITECTURE.md
-- (sections 6, 7, 11, 13, 14, 26) — read that first for the "why" behind
-- these choices. See ../DATABASE-SCHEMA.md for a narrative overview and the
-- handful of simplifications made relative to the PRD's entity sketch.
--
-- Conventions used throughout:
--   - Every table's primary key is `id UUID DEFAULT gen_random_uuid()`.
--   - Every tenant-owned table carries `tenant_id` -> clinics(id), enforced
--     by Postgres Row-Level Security (Section 15) in addition to app-layer
--     scoping (the app must still filter by tenant_id explicitly — RLS is
--     the backstop, not the only mechanism; see PRD §11).
--   - `created_at` / `updated_at` are TIMESTAMPTZ. Tables that model an
--     event or transaction (payments, audit_logs, vitals, ...) have only
--     `created_at` — there is nothing to "update," by design.
--   - Nothing in this schema is ever hard-deleted by application code.
--     Most entities use status transitions instead. A few sensitive tables
--     (`patients`) carry `deleted_at` for soft-delete. `vitals`,
--     `prescriptions`, and `audit_logs` are enforced append-only at the
--     DB level (Section 15) because the product requirement is explicit
--     ("do not overwrite the previous reading; preserve the history").
--   - Polymorphic references (a column pair like `owner_type`/`owner_id` or
--     `source_type`/`source_id`) are used instead of a FK where an entity
--     legitimately points at one of several unrelated tables (documents,
--     invoice line items, audit log targets, inventory transaction
--     references). These are intentionally NOT foreign keys — enforce
--     validity of `owner_type`/`source_type` values in the app layer.
-- =============================================================================


-- =============================================================================
-- 1. EXTENSIONS & HELPER FUNCTIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy patient name search

-- Reads the tenant id the application set for this connection/transaction
-- (via `SET LOCAL app.current_tenant_id = '<uuid>'` at the start of each
-- request). Returns NULL if unset, rather than erroring, so the RLS
-- policies below can fail closed (no tenant set => no rows visible).
CREATE OR REPLACE FUNCTION app_current_tenant_id() RETURNS uuid AS $$
  SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid;
$$ LANGUAGE sql STABLE;

-- Set by the Platform Admin service path only (PRD §11 "Platform Admin
-- bypass"). Every query made through that path is separately audit-logged
-- by the application; this flag is what lets it see across tenants.
CREATE OR REPLACE FUNCTION app_is_platform_admin() RETURNS boolean AS $$
  SELECT COALESCE(NULLIF(current_setting('app.is_platform_admin', true), '')::boolean, false);
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Applied to vitals, prescriptions, and audit_logs: makes the "no
-- overwrite, preserve history" requirement a database guarantee, not just
-- an application convention. The app_is_platform_admin() escape valve
-- (added post-implementation, see DATABASE-SCHEMA.md changelog) exists
-- because these tables also cascade ON DELETE from clinics — normal
-- application code (tenant_session, is_platform_admin=false) is still
-- unconditionally blocked; only the same narrow administrative bypass
-- already used for RLS can also remove these rows, e.g. as a side effect
-- of deleting the tenant that owns them entirely.
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


-- =============================================================================
-- 2. ENUM TYPES
-- =============================================================================

CREATE TYPE clinic_status         AS ENUM ('TRIAL','ACTIVE','SUSPENDED','CANCELLED');
CREATE TYPE subscription_status   AS ENUM ('TRIALING','ACTIVE','PAST_DUE','CANCELLED');
CREATE TYPE user_status           AS ENUM ('INVITED','ACTIVE','INACTIVE','SUSPENDED');
CREATE TYPE appointment_source    AS ENUM ('ONLINE','RECEPTIONIST','WALK_IN');
CREATE TYPE appointment_status    AS ENUM ('SCHEDULED','CHECKED_IN','IN_PROGRESS','COMPLETED','CANCELLED','NO_SHOW');
CREATE TYPE encounter_status      AS ENUM ('OPEN','IN_CONSULTATION','COMPLETED','CANCELLED');
CREATE TYPE queue_token_status    AS ENUM ('WAITING','CALLED','IN_PROGRESS','DONE','NO_SHOW','SKIPPED');
CREATE TYPE inventory_txn_type    AS ENUM ('RECEIVE','DISPENSE','SALE','ADJUST','EXPIRE_WRITE_OFF');
CREATE TYPE lab_order_status      AS ENUM ('ORDERED','SAMPLE_COLLECTED','PROCESSING','COMPLETED','CANCELLED');
CREATE TYPE lab_result_flag       AS ENUM ('NORMAL','LOW','HIGH','CRITICAL');
-- DRAFT/ISSUED (not just UNPAID) and NET_BANKING were added while
-- building the Billing module (migration 0014), by direct instruction —
-- see docs/DATABASE-SCHEMA.md's changelog. ISSUED plays UNPAID's old role.
CREATE TYPE invoice_status        AS ENUM ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','VOID');
CREATE TYPE invoice_line_source   AS ENUM ('CONSULTATION','PROCEDURE','PHARMACY','LAB','OTHER');
CREATE TYPE payment_method        AS ENUM ('CASH','CARD','UPI','NET_BANKING','INSURANCE','OTHER');
CREATE TYPE lead_stage            AS ENUM ('NEW','CONTACTED','QUALIFIED','CONVERTED','LOST');
CREATE TYPE follow_up_status      AS ENUM ('PENDING','DONE','CANCELLED');
CREATE TYPE comm_channel          AS ENUM ('WHATSAPP','SMS','EMAIL','PUSH');
CREATE TYPE comm_status           AS ENUM ('QUEUED','SENT','DELIVERED','FAILED');
CREATE TYPE ai_feature            AS ENUM ('RECEPTIONIST','DOCTOR_ASSISTANT');
CREATE TYPE otp_purpose           AS ENUM ('LOGIN');   -- added during Auth module implementation, see below


-- =============================================================================
-- 3. GLOBAL / PLATFORM REFERENCE TABLES (no tenant_id — not RLS-scoped)
-- =============================================================================

-- Separate credential set from tenant `users` (PRD §12: "entirely separate
-- credential set and login surface from tenant users").
CREATE TABLE platform_admins (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  full_name     text NOT NULL,
  status        user_status NOT NULL DEFAULT 'ACTIVE',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- The tenant root. Every other tenant-owned table's `tenant_id` points here.
CREATE TABLE clinics (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  slug        text NOT NULL UNIQUE,        -- subdomain: {slug}.app-domain.com
  timezone    text NOT NULL DEFAULT 'Asia/Kolkata',
  locale      text NOT NULL DEFAULT 'en-IN',
  gst_number  text,
  status      clinic_status NOT NULL DEFAULT 'TRIAL',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Placeholder catalog — the actual pricing model is an open question
-- (PRD §30, item 3). Shape included now so `subscriptions` has something
-- to reference; expect this table's columns to change once that's decided.
CREATE TABLE plans (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code          text NOT NULL UNIQUE,
  name          text NOT NULL,
  price_inr     numeric(10,2) NOT NULL,
  billing_cycle text NOT NULL DEFAULT 'MONTHLY' CHECK (billing_cycle IN ('MONTHLY','ANNUAL')),
  branch_limit  int,
  seat_limit    int,
  features      jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_active     boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- System-defined roles (OWNER, DOCTOR, RECEPTIONIST, NURSE, LAB_STAFF,
-- PHARMACY_STAFF, OTHER_STAFF, PATIENT — PRD §2). Deliberately NOT
-- tenant-scoped: see docs/DATABASE-SCHEMA.md for why per-tenant custom
-- roles (mentioned as a maybe in PRD §6) were simplified out of v1 in
-- favor of `permission_overrides` doing all the per-clinic customization.
CREATE TABLE roles (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,
  name        text NOT NULL,
  description text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE permissions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,   -- e.g. 'vitals.record'
  module      text NOT NULL,          -- groups permissions in settings UI
  description text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- The default grants behind the PRD §3 matrix.
CREATE TABLE role_permissions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id       UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  UNIQUE (role_id, permission_id)
);


-- =============================================================================
-- 4. TENANCY
-- =============================================================================

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
);

CREATE TABLE subscriptions (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  plan_id              UUID NOT NULL REFERENCES plans(id),
  status               subscription_status NOT NULL DEFAULT 'TRIALING',
  current_period_start timestamptz NOT NULL DEFAULT now(),
  current_period_end   timestamptz,
  cancelled_at         timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Generic per-tenant settings bag (branding, defaults, feature flags).
CREATE TABLE tenant_settings (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  key        text NOT NULL,
  value      jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, key)
);


-- =============================================================================
-- 5. IDENTITY & RBAC
-- =============================================================================

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  role_id       UUID NOT NULL REFERENCES roles(id),
  first_name    text,            -- added while building Doctor Management (see DATABASE-SCHEMA.md changelog)
  last_name     text,
  email         text,
  phone         text,
  password_hash text,             -- nullable: OTP-only patient users have none
  status        user_status NOT NULL DEFAULT 'ACTIVE',
  mfa_enabled   boolean NOT NULL DEFAULT false,
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (email IS NOT NULL OR phone IS NOT NULL)
);
CREATE UNIQUE INDEX ux_users_tenant_email ON users (tenant_id, lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX ux_users_tenant_phone ON users (tenant_id, phone) WHERE phone IS NOT NULL;

CREATE TABLE doctor_profiles (
  user_id            UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  specialization     text,
  registration_number text,
  consultation_fee   numeric(10,2),
  working_hours      jsonb NOT NULL DEFAULT '{}'::jsonb,
  bio                text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE staff_profiles (
  user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  employee_code text,
  designation   text,
  joining_date  date,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_branch_assignments (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  branch_id  UUID NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, branch_id)
);

-- Added while implementing Doctor Management (not in the original PRD §6
-- entity sketch, like otp_codes/user_sessions before it): the "Owner
-- invites staff, staff accept to set credentials" workflow (PRD §5) needs
-- somewhere to hold a hashed, expiring invite token. Generic to any role,
-- not doctor-specific.
CREATE TABLE staff_invites (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  text NOT NULL UNIQUE,
  expires_at  timestamptz NOT NULL,
  accepted_at timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- The mechanism behind PRD §13's two-layer permission resolution: a clinic
-- can grant/revoke one permission for one role, or for one specific staff
-- member, without touching the global `role_permissions` defaults. This is
-- what lets an Owner turn on `vitals.record` for Receptionists at their
-- clinic specifically.
CREATE TABLE permission_overrides (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  role_id       UUID REFERENCES roles(id),
  user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
  permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  granted       boolean NOT NULL,
  created_by    UUID REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK ((role_id IS NOT NULL)::int + (user_id IS NOT NULL)::int = 1)
);
CREATE UNIQUE INDEX ux_perm_override_role ON permission_overrides (tenant_id, role_id, permission_id) WHERE role_id IS NOT NULL;
CREATE UNIQUE INDEX ux_perm_override_user ON permission_overrides (tenant_id, user_id, permission_id) WHERE user_id IS NOT NULL;

-- Added while implementing the Auth module (backend/app/modules/auth) —
-- not in the original entity sketch in PRD-ARCHITECTURE.md §6. Needed to
-- support patient OTP login (§12) with server-side-revocable sessions.
-- See docs/DATABASE-SCHEMA.md for the reasoning.
CREATE TABLE otp_codes (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose       otp_purpose NOT NULL DEFAULT 'LOGIN',
  code_hash     text NOT NULL,
  attempt_count int NOT NULL DEFAULT 0,
  expires_at    timestamptz NOT NULL,
  consumed_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_otp_codes_user_active ON otp_codes (user_id, created_at) WHERE consumed_at IS NULL;

-- Opaque, server-side-tracked refresh tokens (PRD §12) — stored hashed,
-- never the raw token. Enables per-device session listing and revocation
-- ("log out this device").
CREATE TABLE user_sessions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_token_hash text NOT NULL UNIQUE,
  device_label       text,
  ip_address         text,
  user_agent         text,
  issued_at          timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL,
  revoked_at         timestamptz
);
CREATE INDEX ix_user_sessions_user_active ON user_sessions (user_id) WHERE revoked_at IS NULL;


-- =============================================================================
-- 6. PATIENTS, APPOINTMENTS & ENCOUNTERS
-- =============================================================================

CREATE TABLE patients (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id            UUID REFERENCES users(id),   -- set once the patient has portal access
  mrn                text NOT NULL,
  first_name         text NOT NULL,
  last_name          text,
  gender             text CHECK (gender IN ('Male','Female','Other')),
  date_of_birth      date,
  phone              text,
  email              text,
  blood_group        text,
  allergies          text[] NOT NULL DEFAULT '{}',
  chronic_conditions text[] NOT NULL DEFAULT '{}',
  emergency_contact  jsonb,
  address            text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,
  UNIQUE (tenant_id, mrn)
);
CREATE UNIQUE INDEX ux_patients_user ON patients (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX ix_patients_tenant_phone ON patients (tenant_id, phone);
CREATE INDEX ix_patients_name_trgm ON patients USING gin ((first_name || ' ' || coalesce(last_name, '')) gin_trgm_ops);

CREATE TABLE appointments (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id        UUID NOT NULL REFERENCES branches(id),
  patient_id       UUID NOT NULL REFERENCES patients(id),
  doctor_id        UUID REFERENCES users(id),
  source           appointment_source NOT NULL,
  scheduled_at     timestamptz NOT NULL,
  duration_minutes int NOT NULL DEFAULT 15,
  status           appointment_status NOT NULL DEFAULT 'SCHEDULED',
  notes            text,
  cancelled_reason text,
  cancelled_by     UUID REFERENCES users(id),
  cancelled_at     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_appt_branch_time ON appointments (branch_id, scheduled_at);
CREATE INDEX ix_appt_doctor_time ON appointments (doctor_id, scheduled_at);
CREATE INDEX ix_appt_patient ON appointments (patient_id);

-- The hub entity for one clinic visit — see PRD §7 for why this exists
-- separately from Appointment (walk-ins, and every clinical/billing
-- record keys off this, not off Appointment directly).
CREATE TABLE encounters (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id      UUID NOT NULL REFERENCES branches(id),
  appointment_id UUID REFERENCES appointments(id),
  patient_id     UUID NOT NULL REFERENCES patients(id),
  status         encounter_status NOT NULL DEFAULT 'OPEN',
  checked_in_at  timestamptz NOT NULL DEFAULT now(),
  completed_at   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_encounter_appointment ON encounters (appointment_id) WHERE appointment_id IS NOT NULL;
CREATE INDEX ix_encounters_patient ON encounters (patient_id);
CREATE INDEX ix_encounters_branch_date ON encounters (branch_id, checked_in_at);

CREATE TABLE queue_tokens (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id    UUID NOT NULL REFERENCES branches(id),
  encounter_id UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  doctor_id    UUID REFERENCES users(id),
  token_date   date NOT NULL DEFAULT current_date,
  token_number int NOT NULL,
  status       queue_token_status NOT NULL DEFAULT 'WAITING',
  called_at    timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  -- Branch-wide daily sequence. If a clinic wants a separate numbered
  -- sequence per doctor, that's a display-layer grouping on top of this
  -- same branch-wide number, not a second numbering scheme in the DB.
  UNIQUE (branch_id, token_date, token_number)
);
CREATE UNIQUE INDEX ux_queue_encounter ON queue_tokens (encounter_id);

-- Append-only by design (PRD §5.3): a new reading is always a new row,
-- never an update to the previous one. `bmi` is derived so callers never
-- have to (mis)calculate it themselves.
CREATE TABLE vitals (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  encounter_id       UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  patient_id         UUID NOT NULL REFERENCES patients(id),
  recorded_by        UUID NOT NULL REFERENCES users(id),
  recorded_by_role   text NOT NULL,   -- snapshot of the role code at time of recording
  recorded_at        timestamptz NOT NULL DEFAULT now(),
  systolic_bp        int,
  diastolic_bp       int,
  heart_rate         int,
  temperature_celsius numeric(4,1),
  spo2               int,
  weight_kg          numeric(5,2),
  height_cm          numeric(5,2),
  bmi                numeric(5,2) GENERATED ALWAYS AS (
    CASE WHEN weight_kg IS NOT NULL AND height_cm IS NOT NULL AND height_cm > 0
      THEN ROUND((weight_kg / ((height_cm / 100.0) ^ 2))::numeric, 2)
      ELSE NULL END
  ) STORED,
  notes      text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_vitals_encounter ON vitals (encounter_id, recorded_at);
CREATE INDEX ix_vitals_patient ON vitals (patient_id, recorded_at);

CREATE TABLE consultations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  encounter_id    UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  doctor_id       UUID NOT NULL REFERENCES users(id),
  chief_complaint text,
  clinical_notes  text,
  diagnosis_text  text,
  icd10_code      text,
  started_at      timestamptz,
  ended_at        timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (encounter_id)
);


-- =============================================================================
-- 7. PHARMACY
-- =============================================================================

CREATE TABLE medicines (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  name         text NOT NULL,
  generic_name text,
  category     text,
  dosage_form  text,
  unit_price   numeric(10,2) NOT NULL DEFAULT 0,
  sku          text,
  is_active    boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_medicines_sku ON medicines (tenant_id, sku) WHERE sku IS NOT NULL;

CREATE TABLE medicine_batches (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  medicine_id       UUID NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
  batch_number      text NOT NULL,
  expiry_date       date NOT NULL,
  quantity_on_hand  int NOT NULL DEFAULT 0 CHECK (quantity_on_hand >= 0),
  cost_price        numeric(10,2),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (medicine_id, batch_number)
);
CREATE INDEX ix_batches_expiry ON medicine_batches (tenant_id, expiry_date);

-- Stock is a ledger, not a mutable counter (PRD §18): every change to
-- medicine_batches.quantity_on_hand is accompanied by a row here, so
-- stock history is always reconstructable. `reference_type`/`reference_id`
-- is polymorphic (PRESCRIPTION_ITEM | PHARMACY_SALE | MANUAL) rather than
-- an FK, since it can point at either of two unrelated tables.
CREATE TABLE pharmacy_inventory_transactions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  batch_id       UUID NOT NULL REFERENCES medicine_batches(id),
  type           inventory_txn_type NOT NULL,
  quantity_delta int NOT NULL,
  reference_type text,
  reference_id   UUID,
  performed_by   UUID NOT NULL REFERENCES users(id),
  notes          text,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_pharm_txn_batch ON pharmacy_inventory_transactions (batch_id, created_at);

-- OTC sales not tied to a prescription. `invoice_id` FK is added in
-- Section 10 (after `invoices` exists) to avoid a forward reference.
CREATE TABLE pharmacy_sales (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id  UUID NOT NULL REFERENCES branches(id),
  patient_id UUID REFERENCES patients(id),
  invoice_id UUID,
  sold_by    UUID NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);


-- =============================================================================
-- 8. PRESCRIPTIONS
-- =============================================================================

-- Immutable-with-supersession (PRD §5.7, §30): a correction is a new
-- prescription referencing the original via `supersedes_prescription_id`,
-- never an edit. Enforced at the DB level in Section 15.
CREATE TABLE prescriptions (
  id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id                  UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  encounter_id               UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  doctor_id                  UUID NOT NULL REFERENCES users(id),
  supersedes_prescription_id UUID REFERENCES prescriptions(id),
  issued_at                  timestamptz NOT NULL DEFAULT now(),
  created_at                 timestamptz NOT NULL DEFAULT now()
);

-- `medicine_id`'s `REFERENCES medicines(id)` is added by an `ALTER TABLE`
-- once the Pharmacy module creates `medicines` (Consultation/E-Prescription
-- was built first — see docs/DATABASE-SCHEMA.md's changelog) — a table
-- can't reference one that doesn't exist yet. Until then the API only
-- accepts `medicine_name_freetext`. `route` (e.g. "oral", "topical") was
-- added during that same module for the same reason `users.first_name`
-- was: the original sketch omitted a field an actual prescription form
-- needs.
CREATE TABLE prescription_items (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id             UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  prescription_id       UUID NOT NULL REFERENCES prescriptions(id) ON DELETE CASCADE,
  medicine_id           UUID,   -- FK to medicines(id) added once the Pharmacy module exists
  medicine_name_freetext text,   -- for medicines not in the tenant's catalog
  dosage                text,
  frequency             text,
  duration              text,
  route                 text,
  prescribed_quantity   int NOT NULL,
  dispensed_quantity    int NOT NULL DEFAULT 0,
  instructions          text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CHECK (medicine_id IS NOT NULL OR medicine_name_freetext IS NOT NULL),
  CHECK (dispensed_quantity <= prescribed_quantity)
);


-- =============================================================================
-- 9. LABORATORY
-- =============================================================================

CREATE TABLE lab_test_catalog (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  name             text NOT NULL,
  category         text,
  price            numeric(10,2) NOT NULL DEFAULT 0,
  reference_ranges jsonb NOT NULL DEFAULT '{}'::jsonb,   -- may vary by age/sex
  is_active        boolean NOT NULL DEFAULT true,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lab_orders (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  encounter_id        UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  test_id             UUID NOT NULL REFERENCES lab_test_catalog(id),
  ordered_by          UUID NOT NULL REFERENCES users(id),
  status              lab_order_status NOT NULL DEFAULT 'ORDERED',
  ordered_at          timestamptz NOT NULL DEFAULT now(),
  sample_collected_at timestamptz,
  completed_at        timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_lab_orders_encounter ON lab_orders (encounter_id);

CREATE TABLE lab_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  lab_order_id    UUID NOT NULL REFERENCES lab_orders(id) ON DELETE CASCADE,
  parameter       text NOT NULL,
  value           text NOT NULL,
  unit            text,
  reference_range text,
  flag            lab_result_flag NOT NULL DEFAULT 'NORMAL',
  entered_by      UUID NOT NULL REFERENCES users(id),
  finalized_at    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);


-- =============================================================================
-- 10. FINANCIAL
-- =============================================================================

CREATE TABLE invoices (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id     UUID NOT NULL REFERENCES branches(id),
  encounter_id  UUID REFERENCES encounters(id),
  patient_id    UUID NOT NULL REFERENCES patients(id),
  subtotal      numeric(12,2) NOT NULL DEFAULT 0,
  tax           numeric(12,2) NOT NULL DEFAULT 0,
  discount      numeric(12,2) NOT NULL DEFAULT 0,
  total         numeric(12,2) NOT NULL DEFAULT 0,
  status        invoice_status NOT NULL DEFAULT 'DRAFT',    -- derived from payments once ISSUED; app must not set PAID directly
  voided_at     timestamptz,
  voided_reason text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_invoices_patient ON invoices (patient_id);
CREATE INDEX ix_invoices_branch_date ON invoices (branch_id, created_at);

ALTER TABLE pharmacy_sales
  ADD CONSTRAINT fk_pharmacy_sales_invoice FOREIGN KEY (invoice_id) REFERENCES invoices(id);

-- `source_type`/`source_id` is polymorphic (CONSULTATION | PROCEDURE |
-- PHARMACY | LAB | OTHER) rather than an FK, since a line item can point
-- at a consultation, a prescription_item's dispense, or a lab_order.
-- `updated_at` was added while building Billing (migration 0014) — a
-- DRAFT invoice's line items are edited in place (PATCH), not only
-- deleted and recreated, matching this file's own architecture note about
-- keeping that the simple common case.
CREATE TABLE invoice_line_items (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  invoice_id  UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  source_type invoice_line_source NOT NULL,
  source_id   UUID,
  description text NOT NULL,
  quantity    numeric(10,2) NOT NULL DEFAULT 1,
  unit_price  numeric(10,2) NOT NULL,
  total       numeric(12,2) NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_invoice_line_items_invoice ON invoice_line_items (invoice_id);

-- Supports split/partial payment (multiple rows per invoice) and refunds
-- (a row with negative amount + reason) — never mutates a prior payment.
-- `notes` was added while building Billing (migration 0014): this
-- comment always promised "+ reason" but the DDL had no column for it.
CREATE TABLE payments (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  invoice_id        UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  amount            numeric(12,2) NOT NULL,
  method            payment_method NOT NULL,
  gateway_reference text,
  notes             text,
  recorded_by       UUID NOT NULL REFERENCES users(id),
  recorded_at       timestamptz NOT NULL DEFAULT now(),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_payments_invoice ON payments (invoice_id);

CREATE TABLE expenses (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id   UUID NOT NULL REFERENCES branches(id),
  category    text NOT NULL,
  amount      numeric(12,2) NOT NULL,
  vendor      text,
  incurred_at date NOT NULL DEFAULT current_date,
  recorded_by UUID NOT NULL REFERENCES users(id),
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
  -- Receipt attachment: a `documents` row with owner_type='EXPENSE',
  -- owner_id=expenses.id — no receipt_document_id column needed here.
);


-- =============================================================================
-- 11. GENERAL (NON-PHARMACY) INVENTORY
-- =============================================================================

CREATE TABLE inventory_items (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  branch_id         UUID NOT NULL REFERENCES branches(id),
  name              text NOT NULL,
  category          text,
  unit              text,
  quantity_on_hand  numeric(10,2) NOT NULL DEFAULT 0,
  reorder_threshold numeric(10,2),
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE inventory_transactions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  item_id        UUID NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  type           inventory_txn_type NOT NULL,
  quantity_delta numeric(10,2) NOT NULL,
  reference      text,
  performed_by   UUID NOT NULL REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);


-- =============================================================================
-- 12. CRM & COMMUNICATION
-- =============================================================================

-- Deliberately distinct from `patients` — not every inquiry becomes a
-- registered patient (PRD §20).
CREATE TABLE leads (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  name                text NOT NULL,
  phone               text,
  email               text,
  source              text,
  stage               lead_stage NOT NULL DEFAULT 'NEW',
  assigned_to         UUID REFERENCES users(id),
  converted_patient_id UUID REFERENCES patients(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE follow_ups (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id          UUID REFERENCES patients(id),
  lead_id             UUID REFERENCES leads(id),
  assigned_to         UUID NOT NULL REFERENCES users(id),
  due_at              timestamptz NOT NULL,
  status              follow_up_status NOT NULL DEFAULT 'PENDING',
  reason              text,
  auto_generated      boolean NOT NULL DEFAULT false,
  source_encounter_id UUID REFERENCES encounters(id),
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  CHECK (patient_id IS NOT NULL OR lead_id IS NOT NULL)
);

CREATE TABLE notification_templates (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  channel        comm_channel NOT NULL,
  event_key      text NOT NULL,   -- e.g. 'appointment.booked', 'lab_result.ready'
  body_template  text NOT NULL,
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, channel, event_key)
);

-- Every outbound (and, later, inbound) patient/lead touchpoint lands here
-- regardless of trigger (CRM-initiated or system notification) — PRD §20.
CREATE TABLE communication_logs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id         UUID REFERENCES patients(id),
  lead_id            UUID REFERENCES leads(id),
  channel            comm_channel NOT NULL,
  template_id        UUID REFERENCES notification_templates(id),
  status             comm_status NOT NULL DEFAULT 'QUEUED',
  provider_message_id text,
  consent_basis      text,   -- DPDP-alignment: why we were allowed to send this
  sent_at            timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  CHECK (patient_id IS NOT NULL OR lead_id IS NOT NULL)
);


-- =============================================================================
-- 13. PLATFORM RELIABILITY
-- =============================================================================

-- Insert-only (enforced in Section 15). `entity_type`/`entity_id` is
-- polymorphic by design — this table logs against every other table.
CREATE TABLE audit_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  actor_user_id UUID REFERENCES users(id),
  actor_role    text,
  action        text NOT NULL,     -- e.g. 'prescription.create'
  entity_type   text NOT NULL,
  entity_id     UUID,
  before        jsonb,
  after         jsonb,
  ip_address    inet,
  user_agent    text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_entity ON audit_logs (tenant_id, entity_type, entity_id);
CREATE INDEX ix_audit_actor ON audit_logs (tenant_id, actor_user_id, created_at);

-- Polymorphic file index (PRD §15) — `owner_type` values include PATIENT,
-- LAB_ORDER, PRESCRIPTION, INVOICE, EXPENSE, etc. The actual bytes live in
-- S3-compatible storage at `storage_key`; this row is what makes them
-- discoverable without listing the bucket.
CREATE TABLE documents (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  owner_type       text NOT NULL,
  owner_id         UUID NOT NULL,
  storage_key      text NOT NULL,
  mime_type        text,
  file_size_bytes  bigint,
  uploaded_by      UUID REFERENCES users(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_documents_owner ON documents (tenant_id, owner_type, owner_id);


-- =============================================================================
-- 14. RESERVED FOR FUTURE PHASES (PRD §23, §24, ABDM note)
-- =============================================================================
-- These tables exist now, unused by any application code, so the phases
-- that need them (Telemedicine, AI features, ABDM/ABHA — PRD §29 Phases
-- 10-12) don't require a schema migration to grow the core entities later.

CREATE TABLE telemedicine_sessions (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  encounter_id       UUID NOT NULL REFERENCES encounters(id) ON DELETE CASCADE,
  provider_session_id text,
  started_at         timestamptz,
  ended_at           timestamptz,
  recording_url      text,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

-- Every AI call, from day one of AI features, gets logged here (PRD §23's
-- AIGateway choke point) — audit trail for both features, not built yet.
CREATE TABLE ai_interaction_logs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  feature        ai_feature NOT NULL,
  input_redacted text,
  output         text,
  model          text,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE abha_links (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id            UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id           UUID NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  abha_id              text,
  linked_at            timestamptz,
  consent_artifact_ref text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (patient_id)
);


-- =============================================================================
-- 15. TRIGGERS
-- =============================================================================

-- 15a. updated_at maintenance — every "master data / entity" table.
-- (Event/transaction/log tables such as payments, vitals, audit_logs,
-- pharmacy_inventory_transactions, invoice_line_items, communication_logs
-- intentionally have no updated_at — nothing about them is ever updated.)
DO $$
DECLARE
  t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'platform_admins','clinics','plans','branches','subscriptions','tenant_settings',
    'permission_overrides','users','doctor_profiles','staff_profiles','patients',
    'appointments','encounters','queue_tokens','consultations','medicines',
    'medicine_batches','pharmacy_sales','prescription_items','lab_test_catalog',
    'lab_orders','lab_results','invoices','invoice_line_items','expenses','inventory_items','leads',
    'follow_ups','notification_templates','telemedicine_sessions','abha_links'
  ])
  LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_%I_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
      t, t
    );
  END LOOP;
END $$;

-- 15b. Append-only enforcement — the three tables with an explicit
-- "preserve history, never overwrite" product requirement.
CREATE TRIGGER trg_vitals_immutable BEFORE UPDATE OR DELETE ON vitals
  FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();
CREATE TRIGGER trg_prescriptions_immutable BEFORE UPDATE OR DELETE ON prescriptions
  FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();
CREATE TRIGGER trg_audit_logs_immutable BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();


-- =============================================================================
-- 16. ROW-LEVEL SECURITY (PRD §11 — the tenant-isolation backstop)
-- =============================================================================
-- FORCE ROW LEVEL SECURITY matters here: without it, the table owner role
-- (often the same role the app connects as, unless a dedicated low-priv
-- app role is used) bypasses RLS entirely. See docs/DATABASE-SCHEMA.md for
-- the recommended app-role setup.

-- 16a. The tenant root itself: a clinic can only see its own row.
ALTER TABLE clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinics FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON clinics
  USING (id = app_current_tenant_id() OR app_is_platform_admin())
  WITH CHECK (id = app_current_tenant_id() OR app_is_platform_admin());

-- 16b. Every tenant-owned table: standard tenant_id policy.
DO $$
DECLARE
  t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'branches','subscriptions','tenant_settings','users','doctor_profiles',
    'staff_profiles','user_branch_assignments','permission_overrides','otp_codes',
    'user_sessions','patients',
    'appointments','encounters','queue_tokens','vitals','consultations','medicines',
    'medicine_batches','pharmacy_inventory_transactions','pharmacy_sales',
    'prescriptions','prescription_items','lab_test_catalog','lab_orders','lab_results',
    'invoices','invoice_line_items','payments','expenses','inventory_items',
    'inventory_transactions','leads','follow_ups','notification_templates',
    'communication_logs','audit_logs','documents','telemedicine_sessions',
    'ai_interaction_logs','abha_links'
  ])
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = app_current_tenant_id() OR app_is_platform_admin()) WITH CHECK (tenant_id = app_current_tenant_id() OR app_is_platform_admin())',
      t
    );
  END LOOP;
END $$;

-- 16c. Global reference tables (platform_admins, plans, roles, permissions,
-- role_permissions) intentionally have NO RLS — they carry no tenant_id
-- and are meant to be readable by every tenant connection (e.g. every
-- request needs to read `permissions`/`role_permissions` to resolve RBAC).
-- Write access to these should be restricted via database GRANTs to a
-- platform-admin-only DB role, not RLS — see docs/DATABASE-SCHEMA.md.


-- =============================================================================
-- 17. SEED DATA (reference / starting point — not exhaustive, see note)
-- =============================================================================
-- This seeds the eight system roles and a representative permission set
-- covering the PRD §3 matrix. It is a starting point to extend as each
-- module is implemented, not a claim that every possible action in the
-- product is already enumerated here.

INSERT INTO roles (code, name) VALUES
  ('OWNER',          'Clinic Owner'),
  ('DOCTOR',         'Doctor'),
  ('RECEPTIONIST',   'Receptionist'),
  ('NURSE',          'Nurse'),
  ('LAB_STAFF',      'Lab Staff'),
  ('PHARMACY_STAFF', 'Pharmacy Staff'),
  ('OTHER_STAFF',    'Other Staff'),
  ('PATIENT',        'Patient');

INSERT INTO permissions (code, module, description) VALUES
  ('clinic.manage_settings',      'tenancy',       'Manage clinic profile, branding, and branches'),
  ('staff.manage',                'identity',      'Invite/manage staff accounts and role assignments'),
  ('doctor.manage_own_profile',   'identity',      'Doctor edits their own profile/working hours'),
  ('patients.register',           'patients',      'Register new patients / edit demographics'),
  ('patients.view_demographics',  'patients',      'View patient demographic info (not full EMR)'),
  ('patients.view_emr',           'patients',      'View full clinical record'),
  ('appointments.manage',         'appointments',  'Book/reschedule/cancel appointments for any patient'),
  ('appointments.book_own',       'appointments',  'Patient books/cancels their own appointment'),
  ('appointments.view',           'appointments',  'View appointments — Doctor is further scoped to their own schedule'),
  ('doctors.view_directory',      'doctors',       'View the read-only doctor directory (name, specialization, fee, schedule) for booking'),
  ('checkin.manage',              'queue',         'Check in patients, manage walk-ins'),
  ('checkin.view',                'queue',         'View walk-ins/check-ins/encounters — tenant/branch-wide, not row-scoped'),
  ('queue.manage',                'queue',         'Manage queue/token status'),
  ('queue.view',                  'queue',         'View the queue/token board — tenant/branch-wide, not row-scoped'),
  ('vitals.record',               'vitals',        'Record a vitals reading'),
  ('vitals.view',                 'vitals',        'View recorded vitals readings — tenant-wide, not row-scoped'),
  ('consultation.manage',         'clinical',      'Create/edit consultation, diagnosis, clinical notes'),
  ('consultation.view',           'clinical',      'View consultations/clinical notes — Doctor scoped to own, Owner/Nurse tenant-wide'),
  ('prescription.manage',         'clinical',      'Issue e-prescriptions'),
  ('prescription.view',           'clinical',      'View prescriptions — Doctor scoped to own, Owner/Nurse tenant-wide'),
  ('billing.manage',              'billing',       'Create/edit invoices'),
  ('billing.view_own',            'billing',       'Patient views own invoices'),
  ('payments.record',             'billing',       'Record payments against an invoice'),
  ('pharmacy.manage_catalog',     'pharmacy',       'Manage medicine catalog and stock'),
  ('pharmacy.dispense',           'pharmacy',       'Dispense prescriptions / process OTC sales'),
  ('lab.manage_catalog',          'laboratory',     'Manage lab test catalog'),
  ('lab.order',                   'laboratory',     'Order lab tests'),
  ('lab.enter_results',           'laboratory',     'Enter/finalize lab results'),
  ('inventory.manage',            'inventory',      'Manage general (non-pharmacy) inventory'),
  ('expenses.manage',             'finance',        'Record and manage expenses'),
  ('crm.manage',                  'crm',            'Manage leads and follow-ups'),
  ('communications.send',         'communications', 'Send patient/lead communications'),
  ('dashboard.view',              'analytics',      'View owner dashboard, analytics, and reports'),
  ('dashboard.view_own',          'analytics',      'View own revenue/consultation analytics - Doctor only, row-scoped'),
  ('audit.view',                  'security',       'View the tenant audit log'),
  ('branches.manage',             'tenancy',        'Create/edit branches');

-- Default role -> permission grants (the data behind PRD §3's matrix).
-- "C" (configurable) cells from the matrix are seeded at their documented
-- default (e.g. vitals.record: on for Doctor/Nurse, off for Receptionist —
-- an Owner enables it per-clinic via permission_overrides, not by editing
-- this table).
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r, permissions p WHERE (r.code, p.code) IN (
  ('OWNER','clinic.manage_settings'), ('OWNER','staff.manage'), ('OWNER','patients.register'),
  ('OWNER','patients.view_emr'), ('OWNER','patients.view_demographics'), ('OWNER','appointments.manage'),
  ('OWNER','appointments.view'), ('OWNER','checkin.manage'), ('OWNER','checkin.view'),
  ('OWNER','queue.manage'), ('OWNER','queue.view'), ('OWNER','vitals.record'), ('OWNER','vitals.view'),
  ('OWNER','consultation.manage'), ('OWNER','consultation.view'),
  ('OWNER','prescription.manage'), ('OWNER','prescription.view'),
  ('OWNER','billing.manage'),
  ('OWNER','payments.record'), ('OWNER','pharmacy.manage_catalog'), ('OWNER','pharmacy.dispense'),
  ('OWNER','lab.manage_catalog'), ('OWNER','lab.order'), ('OWNER','lab.enter_results'),
  ('OWNER','inventory.manage'), ('OWNER','expenses.manage'), ('OWNER','crm.manage'),
  ('OWNER','communications.send'), ('OWNER','dashboard.view'), ('OWNER','audit.view'),
  ('OWNER','branches.manage'),

  ('DOCTOR','doctor.manage_own_profile'), ('DOCTOR','patients.view_emr'),
  ('DOCTOR','patients.view_demographics'), ('DOCTOR','appointments.view'),
  ('DOCTOR','vitals.record'), ('DOCTOR','vitals.view'),
  ('DOCTOR','checkin.view'), ('DOCTOR','queue.view'),
  ('DOCTOR','consultation.manage'), ('DOCTOR','consultation.view'),
  ('DOCTOR','prescription.manage'), ('DOCTOR','prescription.view'), ('DOCTOR','dashboard.view_own'),
  ('DOCTOR','lab.order'), ('DOCTOR','billing.view_own'),

  ('RECEPTIONIST','patients.register'), ('RECEPTIONIST','patients.view_demographics'),
  ('RECEPTIONIST','appointments.manage'), ('RECEPTIONIST','appointments.view'),
  ('RECEPTIONIST','doctors.view_directory'), ('RECEPTIONIST','checkin.manage'), ('RECEPTIONIST','checkin.view'),
  ('RECEPTIONIST','queue.manage'), ('RECEPTIONIST','queue.view'), ('RECEPTIONIST','vitals.view'),
  ('RECEPTIONIST','billing.manage'),
  ('RECEPTIONIST','payments.record'), ('RECEPTIONIST','crm.manage'),
  ('RECEPTIONIST','communications.send'),

  ('NURSE','patients.view_demographics'), ('NURSE','vitals.record'), ('NURSE','vitals.view'),
  ('NURSE','checkin.view'), ('NURSE','queue.view'),
  ('NURSE','consultation.view'), ('NURSE','prescription.view'),
  ('NURSE','appointments.view'),

  ('LAB_STAFF','lab.order'), ('LAB_STAFF','lab.enter_results'), ('LAB_STAFF','patients.view_demographics'),

  ('PHARMACY_STAFF','pharmacy.manage_catalog'), ('PHARMACY_STAFF','pharmacy.dispense'), ('PHARMACY_STAFF','patients.view_demographics'),

  ('PATIENT','appointments.book_own'), ('PATIENT','billing.view_own'), ('PATIENT','doctors.view_directory')
);

-- Placeholder plan catalog — expect this to be replaced once the
-- subscription/billing model (PRD §30, item 3) is decided.
INSERT INTO plans (code, name, price_inr, billing_cycle, branch_limit, seat_limit) VALUES
  ('STARTER', 'Starter',  1999.00, 'MONTHLY', 1, 10),
  ('GROWTH',  'Growth',   4999.00, 'MONTHLY', 3, 40);
