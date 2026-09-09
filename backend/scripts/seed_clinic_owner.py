"""One-time bootstrap: create the first Clinic (tenant) + its OWNER user.

There is no self-serve clinic-onboarding endpoint in this backend (see
CLAUDE.md's module status table — clinic creation is explicitly out of
scope for the API). This script is the only way to get a real clinic +
its first login into a fresh database — run it once per new clinic
against whatever database DATABASE_URL in backend/.env already points at
(local dev, or a deployed environment's Neon database), the exact same
env var and connection the running app itself uses. It does NOT need
DATABASE_URL_SYNC at all: it goes through the app's own async ORM
session machinery (`app.core.db.platform_admin_session`), the same
narrow, RLS-policy-encoded bypass the test suite's `conftest.py`
fixtures already use to create tenants before any tenant context exists
— not a superuser trick, so it works identically against `app_user` on
Neon as it does against local Postgres.

Usage (run from backend/, with DATABASE_URL already pointed at the
target database — same as `alembic upgrade head` needs):

    .venv/Scripts/python.exe -m scripts.seed_clinic_owner \\
        --clinic-name "Acme Clinic" \\
        --clinic-slug acme-clinic \\
        --owner-first-name Jane \\
        --owner-last-name Doe \\
        --owner-email owner@acme-clinic.example

Omit --owner-password to have one generated and printed once (never
stored in plaintext anywhere, including this script's own output being
piped to a file — copy it immediately, it cannot be recovered after).
Prerequisite: `alembic upgrade head` must have already run against the
same database (this script reads the OWNER role's id from the `roles`
table migration 0001 seeds — an empty `roles` table means migrations
haven't been applied yet, and the script exits with a clear error
rather than a confusing FK/lookup failure).
"""

import argparse
import asyncio
import secrets
import sys

from sqlalchemy import select

from app.core.db import platform_admin_session
from app.core.security import hash_password
from app.modules.auth.models import Role, User, UserStatus
from app.modules.tenancy.models import Branch, Clinic, ClinicStatus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clinic-name", required=True, help='Display name, e.g. "Acme Clinic"')
    parser.add_argument("--clinic-slug", required=True, help="URL-safe unique identifier, e.g. acme-clinic - used as clinic_slug at login")
    parser.add_argument("--owner-first-name", required=True)
    parser.add_argument("--owner-last-name", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--owner-password", default=None, help="Omit to auto-generate a strong random password (printed once)")
    parser.add_argument("--branch-name", default="Main Branch", help='Default: "Main Branch" - every operational module needs at least one branch to exist')
    parser.add_argument("--branch-address", default=None)
    parser.add_argument("--branch-phone", default=None)
    return parser.parse_args()


async def seed(args: argparse.Namespace) -> None:
    owner_password = args.owner_password or secrets.token_urlsafe(18)

    async with platform_admin_session() as session:
        existing = await session.execute(select(Clinic).where(Clinic.slug == args.clinic_slug))
        if existing.scalar_one_or_none() is not None:
            print(f'A clinic with slug "{args.clinic_slug}" already exists - refusing to create a duplicate.', file=sys.stderr)
            print("Pick a different --clinic-slug, or this clinic is already bootstrapped.", file=sys.stderr)
            sys.exit(1)

        owner_role = (await session.execute(select(Role).where(Role.code == "OWNER"))).scalar_one_or_none()
        if owner_role is None:
            print("No OWNER role found in the `roles` table - has `alembic upgrade head` been run against this database yet?", file=sys.stderr)
            sys.exit(1)

        clinic = Clinic(name=args.clinic_name, slug=args.clinic_slug, status=ClinicStatus.ACTIVE)
        session.add(clinic)
        await session.flush()  # populate clinic.id from its server_default before using it as a FK below

        branch = Branch(tenant_id=clinic.id, name=args.branch_name, address=args.branch_address, phone=args.branch_phone)
        session.add(branch)

        owner = User(
            tenant_id=clinic.id,
            role_id=owner_role.id,
            first_name=args.owner_first_name,
            last_name=args.owner_last_name,
            email=args.owner_email,
            password_hash=hash_password(owner_password),
            status=UserStatus.ACTIVE,
        )
        session.add(owner)
        await session.flush()

        clinic_slug, owner_email, owner_id = clinic.slug, owner.email, owner.id
        # Transaction commits on clean exit of the `async with` block (see
        # platform_admin_session's own docstring) — clinic, branch, and
        # owner are created atomically or not at all.

    print("\nClinic created successfully.")
    print(f"  clinic_slug:   {clinic_slug}")
    print(f"  owner_email:   {owner_email}")
    print(f"  owner_user_id: {owner_id}")
    if args.owner_password is None:
        print(f"  owner_password (generated, shown once - save it now): {owner_password}")
    print(f'\nLog in at POST /api/v1/auth/staff/login with {{"clinic_slug": "{clinic_slug}", "identifier": "{owner_email}", "password": "<the password above>"}}')


if __name__ == "__main__":
    asyncio.run(seed(parse_args()))
