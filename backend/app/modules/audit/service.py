"""Audit Logging: PRD-ARCHITECTURE.md §14 — "written via a single audit()
service call invoked from each module's service layer at the point of any
create/update/soft-delete of a clinically, financially, or access-control-
relevant entity — not via a generic ORM hook, so what gets audited (and
what before/after means for that entity) is an explicit per-module
decision, not implicit."

`record()` is a free function, not a method on some `AuditLogService`
instance — deliberately, same pattern as `app.modules.auth.service.
issue_staff_invite`: callers pass in a session that is *already* inside
their own `tenant_session`, so the audit row commits atomically with the
change it describes. Never open a fresh `tenant_session` just to call
this — a failure between the real change and a separately-committed audit
row would either lose the record of what happened or record something
that didn't actually persist.
"""

import uuid

from app.core.db import tenant_session
from app.modules.audit.repository import AuditLogRepository
from app.modules.audit.schemas import AuditLogEntry, AuditLogListResponse


async def record(
    session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    await AuditLogRepository(session).create(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip_address=ip_address,
        user_agent=user_agent,
    )


class AuditLogService:
    """The read side — Owner-only per PRD §14 ("Owner can read their
    tenant's audit log"). Opens its own `tenant_session`, unlike
    `record()`: a read has no write to stay atomic with."""

    async def list_logs(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> AuditLogListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await AuditLogRepository(session).search(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_user_id=actor_user_id,
                limit=limit,
                offset=offset,
            )
            return AuditLogListResponse(
                items=[AuditLogEntry.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
            )
