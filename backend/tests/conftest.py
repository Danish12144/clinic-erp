"""Shared pytest fixtures for the backend test suite (Auth, Tenancy, and
future modules).

Unit tests (tests/unit) never touch a database. Integration and
tenant-isolation tests need a real Postgres with the Auth module's schema
applied (RLS, enums, generated columns are Postgres-specific — SQLite is
not an option here). If TEST_DATABASE_URL / DATABASE_URL isn't reachable,
those tests are skipped rather than failed, so the suite degrades
gracefully in an environment with no DB available while still being fully
real against one that has it (see backend/docker-compose.test.yml).
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "test")

from app.core.config import get_settings  # noqa: E402
from app.core.db import SessionLocal, platform_admin_session  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.models import Role, User  # noqa: E402
from app.modules.patients.models import Patient  # noqa: E402
from app.modules.tenancy.models import Clinic  # noqa: E402

settings = get_settings()


def _database_reachable() -> bool:
    async def _probe() -> bool:
        try:
            dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
            conn = await asyncpg.connect(dsn, timeout=2)
            await conn.close()
            return True
        except Exception:
            return False

    return asyncio.run(_probe())


@pytest.fixture(scope="session")
def db_available() -> bool:
    return _database_reachable()


@pytest_asyncio.fixture
async def require_db(db_available: bool) -> None:
    if not db_available:
        pytest.skip("No reachable Postgres at DATABASE_URL — start backend/docker-compose.test.yml and run migrations")


@pytest_asyncio.fixture
async def test_clinic(require_db: None) -> AsyncIterator[Clinic]:
    """A throwaway clinic tenant, deleted (cascading to its users/sessions/
    OTP codes/overrides) at teardown."""
    slug = f"test-clinic-{uuid.uuid4().hex[:10]}"
    async with platform_admin_session() as session:
        clinic = Clinic(name="Test Clinic", slug=slug)
        session.add(clinic)
        await session.flush()
        clinic_id = clinic.id
        clinic_slug = clinic.slug

    yield Clinic(id=clinic_id, name="Test Clinic", slug=clinic_slug)

    async with platform_admin_session() as session:
        await session.execute(text("DELETE FROM clinics WHERE id = :id"), {"id": str(clinic_id)})


@pytest_asyncio.fixture
async def role_map(require_db: None) -> dict[str, uuid.UUID]:
    """Role codes -> ids, from the seed data the migration inserts."""
    async with platform_admin_session() as session:
        result = await session.execute(select(Role))
        return {role.code: role.id for role in result.scalars().all()}


@pytest_asyncio.fixture
async def make_staff_user(test_clinic: Clinic, role_map: dict[str, uuid.UUID]):
    """Factory fixture: `await make_staff_user(role_code="DOCTOR", email=..., password=...)`
    creates an ACTIVE staff user in `test_clinic` and returns (user_id, raw_password)."""

    async def _create(*, role_code: str, email: str | None = None, phone: str | None = None, password: str = "correct-horse-battery-staple") -> tuple[uuid.UUID, str]:
        async with platform_admin_session() as session:
            user = User(
                tenant_id=test_clinic.id,
                role_id=role_map[role_code],
                email=email,
                phone=phone,
                password_hash=hash_password(password),
            )
            session.add(user)
            await session.flush()
            return user.id, password

    return _create


@pytest_asyncio.fixture
async def make_patient(test_clinic: Clinic):
    """Factory fixture for a clinical Patient record with no linked
    portal user (user_id stays NULL) — the pre-auto-provisioning state
    every real patient starts in, used to test AuthService.
    request_patient_otp's self-service linking rather than the
    already-linked case make_patient_user sets up."""

    async def _create(*, phone: str, first_name: str = "Test", last_name: str | None = None) -> uuid.UUID:
        async with platform_admin_session() as session:
            patient = Patient(
                tenant_id=test_clinic.id, mrn=f"MRN-TEST-{uuid.uuid4().hex[:10]}", first_name=first_name, last_name=last_name, phone=phone,
            )
            session.add(patient)
            await session.flush()
            return patient.id

    return _create


@pytest_asyncio.fixture
async def make_patient_user(test_clinic: Clinic, role_map: dict[str, uuid.UUID]):
    """Factory fixture for a PATIENT-role user with no password (OTP-only login)."""

    async def _create(*, phone: str) -> uuid.UUID:
        async with platform_admin_session() as session:
            user = User(tenant_id=test_clinic.id, role_id=role_map["PATIENT"], phone=phone)
            session.add(user)
            await session.flush()
            return user.id

    return _create


@pytest_asyncio.fixture
async def db_session(require_db: None) -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def login_as(test_clinic: Clinic, make_staff_user, api_client: AsyncClient):
    """Factory fixture: `headers, user_id = await login_as(role_code="OWNER")`
    creates a staff user with that role in `test_clinic`, logs them in via
    the real HTTP endpoint, and returns ready-to-use auth headers plus the
    user id. Reused across modules' integration tests wherever a route
    just needs "some authenticated user with role X"."""

    async def _login(*, role_code: str, email: str | None = None) -> tuple[dict[str, str], uuid.UUID]:
        email = email or f"{role_code.lower()}-{uuid.uuid4().hex[:8]}@test-clinic.example"
        user_id, password = await make_staff_user(role_code=role_code, email=email)
        response = await api_client.post(
            "/api/v1/auth/staff/login",
            json={"clinic_slug": test_clinic.slug, "identifier": email, "password": password},
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, user_id

    return _login


@pytest_asyncio.fixture
async def owner_headers(login_as) -> dict[str, str]:
    headers, _ = await login_as(role_code="OWNER")
    return headers
