import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkin.models import Encounter, EncounterStatus, QueueToken, QueueTokenStatus


class EncounterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, appointment_id: uuid.UUID | None, patient_id: uuid.UUID
    ) -> Encounter:
        encounter = Encounter(tenant_id=tenant_id, branch_id=branch_id, appointment_id=appointment_id, patient_id=patient_id)
        self._session.add(encounter)
        await self._session.flush()
        return encounter

    async def get_by_id(self, encounter_id: uuid.UUID) -> Encounter | None:
        result = await self._session.execute(select(Encounter).where(Encounter.id == encounter_id))
        return result.scalar_one_or_none()

    async def get_by_appointment_id(self, appointment_id: uuid.UUID) -> Encounter | None:
        result = await self._session.execute(select(Encounter).where(Encounter.appointment_id == appointment_id))
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        status: EncounterStatus | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Encounter], int]:
        filters = [Encounter.tenant_id == tenant_id]
        if branch_id:
            filters.append(Encounter.branch_id == branch_id)
        if patient_id:
            filters.append(Encounter.patient_id == patient_id)
        if status:
            filters.append(Encounter.status == status)
        if date_from:
            filters.append(Encounter.checked_in_at >= date_from)
        if date_to:
            filters.append(Encounter.checked_in_at <= date_to)

        count_result = await self._session.execute(select(func.count()).select_from(Encounter).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Encounter).where(*filters).order_by(Encounter.checked_in_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

    async def update_status(self, encounter_id: uuid.UUID, *, status: EncounterStatus) -> None:
        await self._session.execute(
            update(Encounter).where(Encounter.id == encounter_id).values(status=status, updated_at=datetime.now(timezone.utc))
        )


class QueueTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, encounter_id: uuid.UUID, doctor_id: uuid.UUID | None
    ) -> QueueToken:
        """Branch-wide daily sequence (PRD note on the master schema). A
        naive "SELECT MAX(token_number) then INSERT" races two concurrent
        check-ins at the same branch into the same number — the table's
        UNIQUE(branch_id, token_date, token_number) constraint would only
        catch that after the fact, aborting one transaction. A transaction-
        scoped advisory lock keyed by branch serializes issuance for the
        same branch without a broader table lock, and releases itself
        automatically on commit/rollback."""
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"queue_token:{branch_id}"}
        )
        today = datetime.now(timezone.utc).date()
        max_result = await self._session.execute(
            select(func.coalesce(func.max(QueueToken.token_number), 0)).where(
                QueueToken.branch_id == branch_id, QueueToken.token_date == today
            )
        )
        next_number = max_result.scalar_one() + 1
        token = QueueToken(
            tenant_id=tenant_id,
            branch_id=branch_id,
            encounter_id=encounter_id,
            doctor_id=doctor_id,
            token_date=today,
            token_number=next_number,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_by_id(self, token_id: uuid.UUID) -> QueueToken | None:
        result = await self._session.execute(select(QueueToken).where(QueueToken.id == token_id))
        return result.scalar_one_or_none()

    async def get_by_encounter_id(self, encounter_id: uuid.UUID) -> QueueToken | None:
        result = await self._session.execute(select(QueueToken).where(QueueToken.encounter_id == encounter_id))
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        status: QueueTokenStatus | None,
        token_date,
        limit: int,
        offset: int,
    ) -> tuple[list[QueueToken], int]:
        filters = [QueueToken.tenant_id == tenant_id]
        if branch_id:
            filters.append(QueueToken.branch_id == branch_id)
        if doctor_id:
            filters.append(QueueToken.doctor_id == doctor_id)
        if status:
            filters.append(QueueToken.status == status)
        if token_date:
            filters.append(QueueToken.token_date == token_date)

        count_result = await self._session.execute(select(func.count()).select_from(QueueToken).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(QueueToken).where(*filters).order_by(QueueToken.token_number.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

    async def find_next_waiting(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, doctor_id: uuid.UUID | None
    ) -> QueueToken | None:
        today = datetime.now(timezone.utc).date()
        filters = [
            QueueToken.tenant_id == tenant_id,
            QueueToken.branch_id == branch_id,
            QueueToken.token_date == today,
            QueueToken.status == QueueTokenStatus.WAITING,
        ]
        if doctor_id:
            filters.append(QueueToken.doctor_id == doctor_id)
        result = await self._session.execute(select(QueueToken).where(*filters).order_by(QueueToken.token_number.asc()).limit(1))
        return result.scalar_one_or_none()

    async def update_status(self, token_id: uuid.UUID, *, status: QueueTokenStatus, called_at: datetime | None = None) -> None:
        fields: dict[str, object] = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if called_at is not None:
            fields["called_at"] = called_at
        await self._session.execute(update(QueueToken).where(QueueToken.id == token_id).values(**fields))
