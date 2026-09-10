"""Rotate the passwords of the 7 demo accounts `scripts/seed_demo_accounts.py`
created under the 'my-clinic' tenant, away from the hardcoded plaintext
values that script committed to a PUBLIC repo (see CLAUDE.md's audit note
for the incident). This script generates a fresh, strong, random password
per account, sets it, and prints the full set exactly once — nothing is
persisted in plaintext anywhere, same one-time-reveal convention
`seed_clinic_owner.py` already established.

This is a targeted incident-response fix, not a general-purpose tool: it
only touches the 7 specific (tenant_slug, email) pairs `seed_demo_accounts.py`
defined. It does not create accounts (every target must already exist) and
it does not change roles/status, only `password_hash`.

Usage (run from backend/, with DATABASE_URL already pointed at the target
database — same connection the running app itself uses, e.g. the live
Neon database via Koyeb's one-off "Run command", or locally):

    .venv/Scripts/python.exe -m scripts.rotate_demo_account_passwords

After running, immediately update any place these credentials were shared
(notes, docs, a password manager) and treat the old values as permanently
compromised — do not re-run `seed_demo_accounts.py` afterward, since it
would silently reset these accounts back to the old hardcoded passwords.
"""

import asyncio
import secrets
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.core.security import hash_password
from app.modules.auth.models import User
from app.modules.tenancy.models import Clinic

CLINIC_SLUG = "my-clinic"

# Must match scripts/seed_demo_accounts.py's ACCOUNTS list exactly (email only —
# role/name are not touched here).
EMAILS = [
    "admin.myclinic@gmail.com",
    "reception.myclinic@gmail.com",
    "doctor.myclinic@gmail.com",
    "nurse.myclinic@gmail.com",
    "pharmacy.myclinic@gmail.com",
    "store.myclinic@gmail.com",
    "accounts.myclinic@gmail.com",
]


async def rotate() -> None:
    results: list[tuple[str, str]] = []

    async with platform_admin_session() as session:
        clinic = (await session.execute(select(Clinic).where(Clinic.slug == CLINIC_SLUG))).scalar_one_or_none()
        if clinic is None:
            print(f'No clinic with slug "{CLINIC_SLUG}" found on this database - nothing to rotate.', file=sys.stderr)
            sys.exit(1)

        missing: list[str] = []
        for email in EMAILS:
            user = (
                await session.execute(select(User).where(User.tenant_id == clinic.id, User.email == email))
            ).scalar_one_or_none()
            if user is None:
                missing.append(email)
                continue
            new_password = secrets.token_urlsafe(18)
            user.password_hash = hash_password(new_password)
            results.append((email, new_password))

        if missing:
            print(f"Warning: these accounts were not found under '{CLINIC_SLUG}' and were skipped: {missing}", file=sys.stderr)
        # Transaction commits on clean exit of the `async with` block.

    if not results:
        print("No accounts were rotated.", file=sys.stderr)
        sys.exit(1)

    print(f'\nRotated {len(results)} account password(s) under clinic "{CLINIC_SLUG}" (shown once - save these now):\n')
    for email, password in results:
        print(f"  {email:<32} {password}")
    print(f'\nLog in at POST /api/v1/auth/staff/login with {{"clinic_slug": "{CLINIC_SLUG}", "identifier": "<email>", "password": "<password above>"}}')
    print("\nDo NOT re-run scripts/seed_demo_accounts.py after this - it would silently reset these back to the old, compromised hardcoded values.")


if __name__ == "__main__":
    asyncio.run(rotate())
