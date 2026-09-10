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

Usage (run from backend/, DATABASE_URL already pointed at the target DB):

    .venv/Scripts/python.exe -m scripts.seed_demo_accounts
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.core.security import hash_password
from app.modules.auth.models import Role, User, UserStatus
from app.modules.doctors.models import DoctorProfile
from app.modules.tenancy.models import Branch, Clinic, ClinicStatus

CLINIC_SLUG = "my-clinic"
CLINIC_NAME = "My Clinic"

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
            session.add(Branch(tenant_id=clinic.id, name="Main Branch"))
            print(f'Created clinic "{CLINIC_SLUG}" ({clinic.id}).')
        else:
            print(f'Clinic "{CLINIC_SLUG}" already exists ({clinic.id}) - reusing it.')

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
        # Transaction commits on clean exit of the `async with` block.

    print(f'\nDone. Log in at POST /api/v1/auth/staff/login with {{"clinic_slug": "{CLINIC_SLUG}", "identifier": "<email>", "password": "<password>"}}')


if __name__ == "__main__":
    asyncio.run(seed())
