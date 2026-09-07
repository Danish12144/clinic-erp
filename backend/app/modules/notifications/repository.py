import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import CommChannel, CommStatus, CommunicationLog, NotificationTemplate


class NotificationTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> NotificationTemplate:
        template = NotificationTemplate(tenant_id=tenant_id, **fields)
        self._session.add(template)
        await self._session.flush()
        return template

    async def get_by_id(self, template_id: uuid.UUID) -> NotificationTemplate | None:
        result = await self._session.execute(select(NotificationTemplate).where(NotificationTemplate.id == template_id))
        return result.scalar_one_or_none()

    async def get_active(self, *, tenant_id: uuid.UUID, channel: CommChannel, template_key: str) -> NotificationTemplate | None:
        result = await self._session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.tenant_id == tenant_id, NotificationTemplate.channel == channel,
                NotificationTemplate.template_key == template_key, NotificationTemplate.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def update_fields(self, template_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(NotificationTemplate).where(NotificationTemplate.id == template_id).values(**fields))

    async def search(
        self, *, tenant_id: uuid.UUID, channel: CommChannel | None, template_key: str | None, is_active: bool | None,
        limit: int, offset: int,
    ) -> tuple[list[NotificationTemplate], int]:
        filters = [NotificationTemplate.tenant_id == tenant_id]
        if channel:
            filters.append(NotificationTemplate.channel == channel)
        if template_key:
            filters.append(NotificationTemplate.template_key == template_key)
        if is_active is not None:
            filters.append(NotificationTemplate.is_active == is_active)

        count_result = await self._session.execute(select(func.count()).select_from(NotificationTemplate).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(NotificationTemplate).where(*filters).order_by(NotificationTemplate.template_key.asc(), NotificationTemplate.channel.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total


class CommunicationLogRepository:
    """Relocated from `app.modules.crm.repository` in migration 0024 — see
    `app/modules/notifications/models.py`'s module docstring."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, channel: CommChannel, status: CommStatus,
        template_id: uuid.UUID | None = None, rendered_body: str | None = None,
    ) -> CommunicationLog:
        log = CommunicationLog(
            tenant_id=tenant_id, patient_id=patient_id, channel=channel, status=status,
            template_id=template_id, rendered_body=rendered_body,
        )
        self._session.add(log)
        await self._session.flush()
        return log

    async def search(
        self, *, tenant_id: uuid.UUID, channel: CommChannel | None, status: CommStatus | None, patient_id: uuid.UUID | None,
        date_from: datetime | None, date_to: datetime | None, limit: int, offset: int,
    ) -> tuple[list[CommunicationLog], int]:
        filters = [CommunicationLog.tenant_id == tenant_id]
        if channel:
            filters.append(CommunicationLog.channel == channel)
        if status:
            filters.append(CommunicationLog.status == status)
        if patient_id:
            filters.append(CommunicationLog.patient_id == patient_id)
        if date_from:
            filters.append(CommunicationLog.created_at >= date_from)
        if date_to:
            filters.append(CommunicationLog.created_at <= date_to)

        count_result = await self._session.execute(select(func.count()).select_from(CommunicationLog).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(CommunicationLog).where(*filters).order_by(CommunicationLog.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total
