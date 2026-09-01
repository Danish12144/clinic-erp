import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenancy.models import Branch, Clinic, TenantSetting


class ClinicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, clinic_id: uuid.UUID) -> Clinic | None:
        result = await self._session.execute(select(Clinic).where(Clinic.id == clinic_id))
        return result.scalar_one_or_none()

    async def update(self, clinic_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Clinic).where(Clinic.id == clinic_id).values(**fields))


class BranchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        address: str | None,
        phone: str | None,
        timezone_: str | None,
        working_hours: dict,
    ) -> Branch:
        branch = Branch(
            tenant_id=tenant_id,
            name=name,
            address=address,
            phone=phone,
            timezone=timezone_,
            working_hours=working_hours,
        )
        self._session.add(branch)
        await self._session.flush()
        return branch

    async def get_by_id(self, branch_id: uuid.UUID) -> Branch | None:
        result = await self._session.execute(select(Branch).where(Branch.id == branch_id))
        return result.scalar_one_or_none()

    async def list_all(self, *, include_inactive: bool = True) -> list[Branch]:
        query = select(Branch).order_by(Branch.name)
        if not include_inactive:
            query = query.where(Branch.is_active.is_(True))
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def update(self, branch_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Branch).where(Branch.id == branch_id).values(**fields))


class TenantSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, *, tenant_id: uuid.UUID, key: str) -> TenantSetting | None:
        result = await self._session.execute(
            select(TenantSetting).where(TenantSetting.tenant_id == tenant_id, TenantSetting.key == key)
        )
        return result.scalar_one_or_none()

    async def list_all(self, *, tenant_id: uuid.UUID) -> list[TenantSetting]:
        result = await self._session.execute(
            select(TenantSetting).where(TenantSetting.tenant_id == tenant_id).order_by(TenantSetting.key)
        )
        return list(result.scalars().all())

    async def upsert(self, *, tenant_id: uuid.UUID, key: str, value: object) -> TenantSetting:
        existing = await self.get_by_key(tenant_id=tenant_id, key=key)
        if existing is not None:
            existing.value = value
            existing.updated_at = datetime.now(timezone.utc)
            await self._session.flush()
            return existing

        setting = TenantSetting(tenant_id=tenant_id, key=key, value=value)
        self._session.add(setting)
        await self._session.flush()
        return setting

    async def delete(self, *, tenant_id: uuid.UUID, key: str) -> bool:
        existing = await self.get_by_key(tenant_id=tenant_id, key=key)
        if existing is None:
            return False
        await self._session.delete(existing)
        return True
