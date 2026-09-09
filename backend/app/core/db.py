"""Database session management and the multi-tenant Row-Level Security
mechanism described in PRD-ARCHITECTURE.md §11.

Every authenticated request must go through `tenant_session`, which sets a
Postgres session variable (`app.current_tenant_id`) that every tenant-owned
table's RLS policy checks. This is the *backstop* layer of tenant
isolation, not the only one — application code (repositories) must still
filter by tenant_id explicitly; RLS exists to catch the case where that
app-layer filter is ever missed.

`platform_admin_session` bypasses tenant scoping entirely. It exists for
exactly one purpose right now: resolving a clinic slug to a tenant id
during login, before any tenant is known (see
app/modules/auth/repository.py::TenantResolutionRepository). Any future
use of it must be able to justify, in a comment at the call site, why a
single-tenant scope doesn't apply.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

# Disables asyncpg's per-connection server-side prepared-statement cache.
# Required whenever DATABASE_URL might point at a PgBouncer transaction-
# pooling endpoint (e.g. Neon's "-pooler" hostname, the recommended
# endpoint for a multi-worker deploy since it multiplexes many app-level
# connections onto few real Postgres backend connections) — in that mode
# a session's underlying backend connection can change between statements,
# so a prepared statement asyncpg cached against one backend connection
# can vanish out from under it on the next query, surfacing as an
# intermittent "prepared statement ... does not exist" under concurrent
# load, not a reliably reproducible local bug. Harmless against a direct
# (non-pooled) endpoint too — the cache is a minor throughput optimization
# this app's CRUD-shaped query load doesn't meaningfully depend on — so
# it's set unconditionally rather than only when a pooler URL is detected.
_ASYNC_CONNECT_ARGS = {"statement_cache_size": 0}

if settings.environment == "test":
    # pytest-asyncio gives each test its own event loop by default;
    # asyncpg connections are bound to the loop they were opened on, so a
    # pooled connection from one test crashes when reused in the next
    # (Windows' Proactor event loop surfaces this as a confusing
    # "Event loop is closed" / AttributeError on teardown). NullPool opens
    # a fresh connection per session instead of reusing one from a pool,
    # sidestepping the mismatch. Real deployments keep normal pooling.
    engine = create_async_engine(settings.database_url, poolclass=NullPool, connect_args=_ASYNC_CONNECT_ARGS, future=True)
else:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args=_ASYNC_CONNECT_ARGS, future=True)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


async def _set_session_context(session: AsyncSession, *, tenant_id: UUID | None, is_platform_admin: bool) -> None:
    # Postgres's `SET LOCAL name = value` syntax does not accept bind
    # parameters (it's not a normal DML statement) — set_config() is the
    # parameterizable equivalent, and with `is_local=true` (the third
    # argument) it's just as transaction-scoped as SET LOCAL: it resets
    # automatically on commit/rollback, so no tenant context can leak into
    # a pooled connection's next use.
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id) if tenant_id else ""},
    )
    await session.execute(
        text("SELECT set_config('app.is_platform_admin', :flag, true)"),
        {"flag": "true" if is_platform_admin else "false"},
    )


@asynccontextmanager
async def tenant_session(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
    """A DB session scoped by RLS to exactly one tenant. Use this for all
    normal, authenticated request handling. Commits on clean exit, rolls
    back on exception."""
    async with SessionLocal() as session, session.begin():
        await _set_session_context(session, tenant_id=tenant_id, is_platform_admin=False)
        yield session


@asynccontextmanager
async def platform_admin_session() -> AsyncIterator[AsyncSession]:
    """Bypasses tenant RLS entirely. See module docstring — this is a
    narrow, explicitly justified exception, not a general-purpose escape
    hatch."""
    async with SessionLocal() as session, session.begin():
        await _set_session_context(session, tenant_id=None, is_platform_admin=True)
        yield session
