import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        actor_role: str | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        before: dict | None,
        after: dict | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        row = AuditLog(
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
        self._session.add(row)
        await self._session.flush()
        return row

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: str | None,
        entity_id: uuid.UUID | None,
        actor_user_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        filters = [AuditLog.tenant_id == tenant_id]
        if entity_type:
            filters.append(AuditLog.entity_type == entity_type)
        if entity_id:
            filters.append(AuditLog.entity_id == entity_id)
        if actor_user_id:
            filters.append(AuditLog.actor_user_id == actor_user_id)

        count_result = await self._session.execute(select(func.count()).select_from(AuditLog).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(AuditLog).where(*filters).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total
