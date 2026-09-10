"""One-off repair: `scripts/seed_demo_accounts.py` created a `users` row with
role=DOCTOR for doctor.myclinic@gmail.com but never the companion
`doctor_profiles` row that the real POST /doctors provisioning path always
creates alongside it — so every doctor-dependent workflow (walk-in
check-in, appointment slot validation, invoice auto-generate's fee lookup)
422s with "Doctor '<id>' does not exist", since those all join through
doctor_profiles, not just users. Discovered live while running the
golden-path production smoke test.

Idempotent: safe to re-run (upserts by user_id). Sets an open Mon-Sat
09:00-18:00 working_hours (doctors fail-closed otherwise, per CLAUDE.md's
own architecture note) and a nominal consultation_fee so
POST /billing/invoices/auto-generate has something to pull in.

Usage (run from backend/, DATABASE_URL pointed at the target database):

    .venv/Scripts/python.exe -m scripts.fix_demo_doctor_profile
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.modules.doctors.models import DoctorProfile
from app.modules.tenancy.models import Clinic
from app.modules.auth.models import User

CLINIC_SLUG = "my-clinic"
DOCTOR_EMAIL = "doctor.myclinic@gmail.com"

OPEN_HOURS = {"open": "09:00", "close": "18:00"}
WORKING_HOURS = {day: OPEN_HOURS for day in ("mon", "tue", "wed", "thu", "fri", "sat")}


async def fix() -> None:
    async with platform_admin_session() as session:
        clinic = (await session.execute(select(Clinic).where(Clinic.slug == CLINIC_SLUG))).scalar_one_or_none()
        if clinic is None:
            print(f'No clinic with slug "{CLINIC_SLUG}" found.', file=sys.stderr)
            sys.exit(1)

        user = (
            await session.execute(select(User).where(User.tenant_id == clinic.id, User.email == DOCTOR_EMAIL))
        ).scalar_one_or_none()
        if user is None:
            print(f"No user {DOCTOR_EMAIL} found under {CLINIC_SLUG}.", file=sys.stderr)
            sys.exit(1)

        profile = (
            await session.execute(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
        ).scalar_one_or_none()
        if profile is None:
            session.add(
                DoctorProfile(
                    user_id=user.id,
                    tenant_id=clinic.id,
                    specialization="General Medicine",
                    consultation_fee=500.00,
                    working_hours=WORKING_HOURS,
                )
            )
            print(f"Created doctor_profiles row for {DOCTOR_EMAIL} ({user.id}).")
        else:
            profile.working_hours = WORKING_HOURS
            profile.consultation_fee = profile.consultation_fee or 500.00
            print(f"doctor_profiles row already existed for {DOCTOR_EMAIL} - refreshed working_hours/fee.")


if __name__ == "__main__":
    asyncio.run(fix())
