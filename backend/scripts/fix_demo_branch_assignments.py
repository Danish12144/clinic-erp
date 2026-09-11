"""One-off repair: none of `scripts/seed_demo_accounts.py`'s 7 demo
accounts ever got a `user_branch_assignments` row (that script only ever
inserted `users` rows, plus a `doctor_profiles` row since
`fix_demo_doctor_profile.py`) -- discovered live when the staff
Appointments page refused to show a booking calendar for the demo doctor
("This doctor isn't assigned to any branch yet"). `UserBranchAssignment`
is schema-ready and generic to any role (Staff Management reuses the same
table), but nothing ever populated it for these accounts.

Confirmed this is a pure data gap, not a real backend constraint:
`AppointmentService._validate_slot` never checks branch assignment at
all (only branch-exists, doctor-exists/active, working_hours, and
conflicting appointments) -- `branch_ids` is purely a staff-side UI signal
(a real, useful one for multi-branch clinics, blocking booking until
someone deliberately picks a sensible branch), not a server-side
restriction. Patient Portal booking was never affected, since its dialog
auto-selects the clinic's own first branch independently of the doctor's
`branch_ids`.

Idempotent: safe to re-run (BranchAssignmentRepository.set_branch_assignments
deletes-then-inserts). Assigns *every active user in the tenant*, not just
the 7 seeded demo accounts -- broadened after the first run surfaced a
second, separate case live: "Aman pratap," a real doctor created through
the actual Staff Directory "Invite staff" UI (not this seed script),
which turned out to have the exact same gap for a different, root-cause
reason -- confirmed by grepping the whole frontend for branch_ids: it's
referenced only in features/doctors/hooks.ts and types.ts, never in an
actual page or dialog. There is currently no UI anywhere that lets a
clinic set or edit a staff/doctor's branch assignment, so every account
created through the real invite flow ends up branch-less permanently,
same as the demo accounts did for their own, different reason. This
script papers over that for every account that exists *right now*; it
does not fix the underlying gap for the *next* one created (see the
product-owner conversation this was flagged in).

Usage (run from backend/, DATABASE_URL pointed at the target database):

    .venv/Scripts/python.exe -m scripts.fix_demo_branch_assignments
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.modules.auth.models import User, UserStatus
from app.modules.doctors.repository import BranchAssignmentRepository
from app.modules.tenancy.models import Branch, Clinic

CLINIC_SLUG = "my-clinic"


async def fix() -> None:
    async with platform_admin_session() as session:
        clinic = (await session.execute(select(Clinic).where(Clinic.slug == CLINIC_SLUG))).scalar_one_or_none()
        if clinic is None:
            print(f'No clinic with slug "{CLINIC_SLUG}" found.', file=sys.stderr)
            sys.exit(1)

        branch = (
            await session.execute(select(Branch).where(Branch.tenant_id == clinic.id).order_by(Branch.created_at))
        ).scalars().first()
        if branch is None:
            print(f'Clinic "{CLINIC_SLUG}" has no branches at all.', file=sys.stderr)
            sys.exit(1)
        print(f'Assigning to branch "{branch.name}" ({branch.id}).')

        users = (
            await session.execute(select(User).where(User.tenant_id == clinic.id, User.status == UserStatus.ACTIVE))
        ).scalars().all()
        # Branch assignment is a staff concept — User.role is lazy="joined"
        # so this filter costs no extra query. Excluding PATIENT here is
        # deliberate: a patient (e.g. a portal test account) has no
        # business being scoped to a branch the way staff/doctors are.
        staff_users = [u for u in users if u.role.code != "PATIENT"]

        repo = BranchAssignmentRepository(session)
        for user in staff_users:
            label = user.email or user.phone or str(user.id)
            existing = await repo.get_branch_ids(user.id)
            if branch.id in existing:
                print(f"  already  {label:<32} already assigned")
                continue
            await repo.set_branch_assignments(tenant_id=clinic.id, user_id=user.id, branch_ids=[*existing, branch.id])
            print(f"  assigned {label:<32} -> {branch.name}")


if __name__ == "__main__":
    asyncio.run(fix())
