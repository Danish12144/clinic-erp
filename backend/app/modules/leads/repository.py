import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.leads.models import Lead, LeadInteraction, LeadSource, LeadStatus


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> Lead:
        lead = Lead(tenant_id=tenant_id, **fields)
        self._session.add(lead)
        await self._session.flush()
        return lead

    async def get_by_id(self, lead_id: uuid.UUID) -> Lead | None:
        result = await self._session.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()

    async def update_fields(self, lead_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Lead).where(Lead.id == lead_id).values(**fields))

    async def search(
        self, *, tenant_id: uuid.UUID, status: LeadStatus | None, source: LeadSource | None,
        assigned_to_user_id: uuid.UUID | None, date_from: datetime | None, date_to: datetime | None,
        limit: int, offset: int,
    ) -> tuple[list[Lead], int]:
        filters = [Lead.tenant_id == tenant_id]
        if status:
            filters.append(Lead.status == status)
        if source:
            filters.append(Lead.source == source)
        if assigned_to_user_id:
            filters.append(Lead.assigned_to_user_id == assigned_to_user_id)
        if date_from:
            filters.append(Lead.created_at >= date_from)
        if date_to:
            filters.append(Lead.created_at <= date_to)

        count_result = await self._session.execute(select(func.count()).select_from(Lead).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Lead).where(*filters).order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total


class LeadInteractionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID, interaction_type: str, outcome: str | None,
        notes: str | None, performed_by: uuid.UUID,
    ) -> LeadInteraction:
        interaction = LeadInteraction(
            tenant_id=tenant_id, lead_id=lead_id, interaction_type=interaction_type, outcome=outcome,
            notes=notes, performed_by=performed_by,
        )
        self._session.add(interaction)
        await self._session.flush()
        return interaction
