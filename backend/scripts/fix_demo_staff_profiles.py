"""One-off repair: `scripts/seed_demo_accounts.py` created bare `users` rows
for its 5 non-doctor demo accounts (reception/nurse/pharmacy/store/accounts)
but never the companion `staff_profiles` row that the real POST /staff
provisioning path always creates alongside it — so `StaffRepository.search()`
(the query behind `GET /api/v1/staff`, which the Staff Directory frontend
page calls) INNER JOINs `users` with `staff_profiles` and silently omits
every one of these 5 accounts from the list, with no error at all. Exactly
the same class of gap `scripts/fix_demo_doctor_profile.py` already fixed
for the DOCTOR account, just never caught until a later pass.

Idempotent: safe to re-run (upserts by user_id, only inserts if missing).
Does NOT touch `seed_demo_accounts.py`'s credentials/roles — this only adds
the missing profile row, so it's safe to run against the live database even
after that script's own credential rotation (see CLAUDE.md's "PRD compliance
audit — 2026-09-10" note on why `seed_demo_accounts.py` itself must not be
re-run there).

Usage (run from backend/, DATABASE_URL pointed at the target database):

    .venv/Scripts/python.exe -m scripts.fix_demo_staff_profiles
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.modules.auth.models import User
from app.modules.staff.models import StaffProfile
from app.modules.tenancy.models import Clinic

CLINIC_SLUG = "my-clinic"

# (email, designation) — designation is cosmetic only, shown in the Staff
# Directory's "Designation / Specialization" column.
STAFF_EMAILS = [
    ("reception.myclinic@gmail.com", "Reception"),
    ("nurse.myclinic@gmail.com", "Nurse"),
    ("pharmacy.myclinic@gmail.com", "Pharmacist"),
    ("store.myclinic@gmail.com", "Store Manager"),
    ("accounts.myclinic@gmail.com", "Accountant"),
]


async def fix() -> None:
    async with platform_admin_session() as session:
        clinic = (await session.execute(select(Clinic).where(Clinic.slug == CLINIC_SLUG))).scalar_one_or_none()
        if clinic is None:
            print(f'No clinic with slug "{CLINIC_SLUG}" found.', file=sys.stderr)
            sys.exit(1)

        for email, designation in STAFF_EMAILS:
            user = (
                await session.execute(select(User).where(User.tenant_id == clinic.id, User.email == email))
            ).scalar_one_or_none()
            if user is None:
                print(f"No user {email} found under {CLINIC_SLUG} - skipping.", file=sys.stderr)
                continue

            profile = (
                await session.execute(select(StaffProfile).where(StaffProfile.user_id == user.id))
            ).scalar_one_or_none()
            if profile is None:
                session.add(StaffProfile(user_id=user.id, tenant_id=clinic.id, designation=designation))
                print(f"Created staff_profiles row for {email} ({user.id}).")
            else:
                print(f"staff_profiles row already existed for {email} - nothing to do.")


if __name__ == "__main__":
    asyncio.run(fix())
