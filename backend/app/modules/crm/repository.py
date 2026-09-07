import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.crm.models import FollowUp, FollowUpStatus


def _with_relations(query):
    return query.options(selectinload(FollowUp.reminder)).execution_options(populate_existing=True)


_OVERDUE_ELIGIBLE = (FollowUpStatus.PENDING, FollowUpStatus.SENT)


class FollowUpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, doctor_id: uuid.UUID | None, encounter_id: uuid.UUID | None, due_at: datetime, reason: str | None, reminder_log_id: uuid.UUID | None, created_by: uuid.UUID) -> FollowUp:
        follow_up = FollowUp(
            tenant_id=tenant_id, patient_id=patient_id, doctor_id=doctor_id, encounter_id=encounter_id, due_at=due_at,
            reason=reason, reminder_log_id=reminder_log_id, created_by=created_by,
        )
        self._session.add(follow_up)
        await self._session.flush()
        return follow_up

    async def get_by_id(self, follow_up_id: uuid.UUID) -> FollowUp | None:
        result = await self._session.execute(_with_relations(select(FollowUp).where(FollowUp.id == follow_up_id)))
        return result.unique().scalar_one_or_none()

    async def update_fields(self, follow_up_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(FollowUp).where(FollowUp.id == follow_up_id).values(**fields))

    async def sweep_overdue(self, *, tenant_id: uuid.UUID) -> None:
        """Lazily transitions any `PENDING`/`SENT` row past its `due_at`
        to `OVERDUE` — see migration 0019's docstring for why this is
        sweep-on-read rather than a scheduled job. Called before every
        search/get in this module so a caller never sees a stale status."""
        await self._session.execute(
            update(FollowUp)
            .where(FollowUp.tenant_id == tenant_id, FollowUp.status.in_(_OVERDUE_ELIGIBLE), FollowUp.due_at < datetime.now(timezone.utc))
            .values(status=FollowUpStatus.OVERDUE, updated_at=datetime.now(timezone.utc))
        )

    async def search(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, doctor_id: uuid.UUID | None,
        status: FollowUpStatus | None, due_from: datetime | None, due_to: datetime | None, overdue_only: bool,
        limit: int, offset: int,
    ) -> tuple[list[FollowUp], int]:
        filters = [FollowUp.tenant_id == tenant_id]
        if patient_id:
            filters.append(FollowUp.patient_id == patient_id)
        if doctor_id:
            filters.append(FollowUp.doctor_id == doctor_id)
        if status:
            filters.append(FollowUp.status == status)
        if due_from:
            filters.append(FollowUp.due_at >= due_from)
        if due_to:
            filters.append(FollowUp.due_at <= due_to)
        if overdue_only:
            filters.append(FollowUp.status == FollowUpStatus.OVERDUE)

        count_result = await self._session.execute(select(func.count()).select_from(FollowUp).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(_with_relations(select(FollowUp).where(*filters)).order_by(FollowUp.due_at.asc()).limit(limit).offset(offset))
        return list(page_result.unique().scalars().all()), total
