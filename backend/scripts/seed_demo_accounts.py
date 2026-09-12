"""One-off demo seeding: creates (or resets) tenant 'my-clinic' plus one
login-ready account per role, matching a specific demo credential list
handed down outside the normal PRD role vocabulary.

This is NOT a general-purpose seeding mechanism and NOT a replacement for
the real staff/doctor invite-and-accept-invite flow (see
`app/modules/auth/service.py::issue_staff_invite` and this repo's
CLAUDE.md "Staff account provisioning" note) — POST /staff and POST
/doctors are unchanged by this script. It exists solely to get these 7
specific demo accounts into an ACTIVE, password-set state without an
invite round-trip, the same "go straight through the ORM inside
platform_admin_session" pattern `scripts/seed_clinic_owner.py` already
uses for the very first Owner login.

Role-name note: the requested list included PHARMACIST, STORE_MANAGER,
and ACCOUNTANT, none of which exist in this system's fixed 8-role model
(OWNER/DOCTOR/RECEPTIONIST/NURSE/LAB_STAFF/PHARMACY_STAFF/OTHER_STAFF/
PATIENT — see migration 0001 and app/modules/auth/models.py::Role's own
docstring, "System-defined roles only... per-clinic customization is
entirely through PermissionOverride, not custom roles"). Per explicit
product-owner instruction, these three map onto the closest existing
role instead of adding new roles to the schema:
  - PHARMACIST      -> PHARMACY_STAFF
  - STORE_MANAGER   -> OTHER_STAFF
  - ACCOUNTANT      -> OTHER_STAFF

Idempotent: safe to re-run. The clinic is created once (slug 'my-clinic'
must not already exist under a different intent); each of the 7 users is
upserted by (tenant_id, email) — an existing row gets its role_id,
password_hash, and status overwritten to match this script's table,
a fresh row gets created.

Any DOCTOR-role account also gets a companion `doctor_profiles` row
upserted alongside its `users` row (open Mon-Sat working hours + a nominal
consultation_fee) — discovered missing live, during a production
golden-path smoke test, after this script originally only inserted the
`users` row: every doctor-dependent workflow (walk-in check-in, appointment
slot validation, invoice auto-generate's fee lookup) joins through
doctor_profiles, not just users, and 422s with "Doctor does not exist"
without one. See `scripts/fix_demo_doctor_profile.py` for the one-off
repair this same fix was back-ported from.

Every non-DOCTOR account likewise gets a companion `staff_profiles` row —
the exact same class of gap as the doctor_profiles one above, just never
caught until a later pass: `StaffRepository.search()` (the query behind
`GET /api/v1/staff`, which the Staff Directory frontend page calls) INNER
JOINs `users` with `staff_profiles`, so a `User` row with no matching
`staff_profiles` row is invisible to that endpoint — silently, no error,
it just never shows up in the list. This script always only inserted the
bare `users` row for these 5 accounts, so they've never actually been
visible in the Staff Directory. See `scripts/fix_demo_staff_profiles.py`
for the one-off repair this same fix was back-ported from.

Every account (not just DOCTOR) also gets a `user_branch_assignments` row
for the clinic's first branch — discovered missing live too, the same
way: the staff Appointments page refuses to show a booking calendar for
a doctor with no branch assignment ("This doctor isn't assigned to any
branch yet"). `UserBranchAssignment` is generic to any role (Staff
Management reuses the same table), so this isn't doctor-specific the way
the profile fix above is. See `scripts/fix_demo_branch_assignments.py`
for the one-off repair this was back-ported from — that script also
covers every *other* active user in the tenant (accounts created through
the real invite flow, which has its own, different version of this gap:
no UI anywhere currently lets you set a branch at invite time), which
this seed script deliberately does not attempt, since it only owns its
own 7 fixed accounts.

Usage (run from backend/, DATABASE_URL already pointed at the target DB):

    .venv/Scripts/python.exe -m scripts.seed_demo_accounts
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.core.security import hash_password
from app.modules.auth.models import Permission, PermissionOverride, Role, User, UserStatus
from app.modules.doctors.models import DoctorProfile
from app.modules.doctors.repository import BranchAssignmentRepository
from app.modules.staff.models import StaffProfile
from app.modules.tenancy.models import Branch, Clinic, ClinicStatus

CLINIC_SLUG = "my-clinic"
CLINIC_NAME = "My Clinic"

# Mirrors app/modules/staff/schemas.py::StaffRoleCode — the roles the real
# Staff Management module (staff_profiles) actually covers. OWNER and
# DOCTOR are deliberately not in this set (DOCTOR gets doctor_profiles
# instead, handled separately above; OWNER gets neither).
STAFF_ROLE_CODES = ("RECEPTIONIST", "NURSE", "LAB_STAFF", "PHARMACY_STAFF", "OTHER_STAFF")

# Phase 1 (Master Handoff item 4, "Accountant permission bundle") — this
# demo tenant's one finance/accounts persona (mapped onto OTHER_STAFF,
# same role-name-collapse this script's own docstring already explains
# for PHARMACIST/STORE_MANAGER) gets these three permissions as per-user
# `permission_overrides`, not a role-wide grant — exactly the mechanism
# migration 0032's docstring describes ("Applying the bundle to a real
# person is what permission_overrides is for"). `billing.view`/
# `expenses.view` are new in migration 0032; `dashboard.view` already
# existed (migration 0015) but OTHER_STAFF never held it by default.
ACCOUNTANT_EMAIL = "accounts.myclinic@gmail.com"
ACCOUNTANT_PERMISSION_CODES = ("billing.view", "expenses.view", "dashboard.view")

# Doctors fail-closed with no working_hours (every day parses to "closed"),
# and invoice auto-generate 422s with no consultation_fee — see this
# script's own docstring for how this was discovered.
_OPEN_HOURS = {"open": "09:00", "close": "18:00"}
DOCTOR_WORKING_HOURS = {day: _OPEN_HOURS for day in ("mon", "tue", "wed", "thu", "fri", "sat")}
DOCTOR_CONSULTATION_FEE = 500.00

# (email, password, role_code, first_name, last_name)
ACCOUNTS = [
    ("admin.myclinic@gmail.com", "Admin@12345", "OWNER", "Clinic", "Admin"),
    ("reception.myclinic@gmail.com", "Demo@12345", "RECEPTIONIST", "Front Desk", "Reception"),
    ("doctor.myclinic@gmail.com", "Demo@12345", "DOCTOR", "Demo", "Doctor"),
    ("nurse.myclinic@gmail.com", "Demo@12345", "NURSE", "Demo", "Nurse"),
    ("pharmacy.myclinic@gmail.com", "Demo@12345", "PHARMACY_STAFF", "Demo", "Pharmacist"),
    ("store.myclinic@gmail.com", "Demo@12345", "OTHER_STAFF", "Demo", "Store Manager"),
    ("accounts.myclinic@gmail.com", "Demo@1234", "OTHER_STAFF", "Demo", "Accountant"),
]


async def seed() -> None:
    async with platform_admin_session() as session:
        clinic = (await session.execute(select(Clinic).where(Clinic.slug == CLINIC_SLUG))).scalar_one_or_none()
        if clinic is None:
            clinic = Clinic(name=CLINIC_NAME, slug=CLINIC_SLUG, status=ClinicStatus.ACTIVE)
            session.add(clinic)
            await session.flush()
            branch = Branch(tenant_id=clinic.id, name="Main Branch")
            session.add(branch)
            await session.flush()
            print(f'Created clinic "{CLINIC_SLUG}" ({clinic.id}).')
        else:
            branch = (
                await session.execute(select(Branch).where(Branch.tenant_id == clinic.id).order_by(Branch.created_at))
            ).scalars().first()
            print(f'Clinic "{CLINIC_SLUG}" already exists ({clinic.id}) - reusing it.')
        if branch is None:
            print(f'Clinic "{CLINIC_SLUG}" has no branches at all - cannot assign one.', file=sys.stderr)
            sys.exit(1)

        branch_repo = BranchAssignmentRepository(session)

        roles = {r.code: r for r in (await session.execute(select(Role))).scalars().all()}
        missing_roles = {role_code for _, _, role_code, _, _ in ACCOUNTS} - set(roles)
        if missing_roles:
            print(f"Missing role(s) in `roles` table: {missing_roles} - has `alembic upgrade head` run?", file=sys.stderr)
            sys.exit(1)

        for email, password, role_code, first_name, last_name in ACCOUNTS:
            existing = (
                await session.execute(select(User).where(User.tenant_id == clinic.id, User.email == email))
            ).scalar_one_or_none()
            if existing is None:
                user = User(
                    tenant_id=clinic.id,
                    role_id=roles[role_code].id,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password_hash=hash_password(password),
                    status=UserStatus.ACTIVE,
                )
                session.add(user)
                await session.flush()  # populate user.id from its server_default before using it as a FK below
                print(f"  created  {email:<32} role={role_code:<14} status=ACTIVE")
            else:
                user = existing
                user.role_id = roles[role_code].id
                user.password_hash = hash_password(password)
                user.status = UserStatus.ACTIVE
                print(f"  updated  {email:<32} role={role_code:<14} status=ACTIVE")

            if role_code == "DOCTOR":
                profile = (
                    await session.execute(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
                ).scalar_one_or_none()
                if profile is None:
                    session.add(
                        DoctorProfile(
                            user_id=user.id,
                            tenant_id=clinic.id,
                            specialization="General Medicine",
                            consultation_fee=DOCTOR_CONSULTATION_FEE,
                            working_hours=DOCTOR_WORKING_HOURS,
                        )
                    )
                    print(f"           + created doctor_profiles row (working_hours, consultation_fee)")
                else:
                    profile.working_hours = DOCTOR_WORKING_HOURS
                    profile.consultation_fee = profile.consultation_fee or DOCTOR_CONSULTATION_FEE
                    print(f"           + doctor_profiles row already existed - refreshed")
            elif role_code in STAFF_ROLE_CODES:
                # Owner is deliberately excluded — it's neither a DOCTOR nor
                # one of the five real Staff Management roles, and giving it
                # a staff_profiles row would make it show up in GET
                # /api/v1/staff (the Staff Directory's "staff" half)
                # alongside the actual staff, which the real POST /staff
                # provisioning path would never do either.
                staff_profile = (
                    await session.execute(select(StaffProfile).where(StaffProfile.user_id == user.id))
                ).scalar_one_or_none()
                if staff_profile is None:
                    session.add(StaffProfile(user_id=user.id, tenant_id=clinic.id, designation=last_name))
                    print(f"           + created staff_profiles row")

            existing_branch_ids = await branch_repo.get_branch_ids(user.id)
            if branch.id not in existing_branch_ids:
                await branch_repo.set_branch_assignments(
                    tenant_id=clinic.id, user_id=user.id, branch_ids=[*existing_branch_ids, branch.id]
                )
                print(f"           + assigned to branch '{branch.name}'")

            if email == ACCOUNTANT_EMAIL:
                for code in ACCOUNTANT_PERMISSION_CODES:
                    permission = (await session.execute(select(Permission).where(Permission.code == code))).scalar_one_or_none()
                    if permission is None:
                        print(f"           ! permission '{code}' not found - has `alembic upgrade head` run?", file=sys.stderr)
                        continue
                    override = (
                        await session.execute(
                            select(PermissionOverride).where(
                                PermissionOverride.tenant_id == clinic.id,
                                PermissionOverride.user_id == user.id,
                                PermissionOverride.permission_id == permission.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if override is None:
                        session.add(
                            PermissionOverride(tenant_id=clinic.id, user_id=user.id, permission_id=permission.id, granted=True)
                        )
                        print(f"           + granted override '{code}'")
                    elif not override.granted:
                        override.granted = True
                        print(f"           + re-granted override '{code}'")
        # Transaction commits on clean exit of the `async with` block.

    print(f'\nDone. Log in at POST /api/v1/auth/staff/login with {{"clinic_slug": "{CLINIC_SLUG}", "identifier": "<email>", "password": "<password>"}}')


if __name__ == "__main__":
    asyncio.run(seed())
