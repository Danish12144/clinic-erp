import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Role, User, UserStatus
from app.modules.staff.models import StaffProfile


class StaffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_role_id(self, code: str) -> uuid.UUID:
        result = await self._session.execute(select(Role.id).where(Role.code == code))
        return result.scalar_one()

    async def create_user(
        self, *, tenant_id: uuid.UUID, role_id: uuid.UUID, first_name: str, last_name: str | None, email: str | None, phone: str | None
    ) -> User:
        user = User(
            tenant_id=tenant_id,
            role_id=role_id,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            status=UserStatus.INVITED,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def create_profile(
        self,
        *,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        employee_code: str | None,
        designation: str | None,
        joining_date,
    ) -> StaffProfile:
        profile = StaffProfile(
            user_id=user_id, tenant_id=tenant_id, employee_code=employee_code, designation=designation, joining_date=joining_date
        )
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_user_and_profile(self, user_id: uuid.UUID) -> tuple[User, StaffProfile] | None:
        user_result = await self._session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return None
        profile_result = await self._session.execute(select(StaffProfile).where(StaffProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        if profile is None:
            return None
        return user, profile

    async def update_user(self, user_id: uuid.UUID, **fields: object) -> None:
        if not fields:
            return
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(User).where(User.id == user_id).values(**fields))

    async def update_profile(self, user_id: uuid.UUID, **fields: object) -> None:
        if not fields:
            return
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(StaffProfile).where(StaffProfile.user_id == user_id).values(**fields))

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        role_code: str | None,
        query_text: str | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[User, StaffProfile]], int]:
        filters = [User.tenant_id == tenant_id, StaffProfile.user_id == User.id]
        if not include_inactive:
            # Same convention as Doctor Management's search: "inactive"
            # means deactivated, not "not yet accepted their invite" — a
            # freshly invited staff member should still be visible.
            filters.append(User.status != UserStatus.INACTIVE)
        if role_code:
            filters.append(Role.code == role_code)
        name_expr = func.concat(User.first_name, " ", func.coalesce(User.last_name, ""))
        if query_text:
            filters.append(func.similarity(name_expr, query_text) > 0.2)

        base = select(User, StaffProfile).join(StaffProfile, StaffProfile.user_id == User.id)
        if role_code:
            base = base.join(Role, Role.id == User.role_id)

        count_query = select(func.count()).select_from(User).join(StaffProfile, StaffProfile.user_id == User.id)
        if role_code:
            count_query = count_query.join(Role, Role.id == User.role_id)
        count_result = await self._session.execute(count_query.where(*filters))
        total = count_result.scalar_one()

        page_query = base.where(*filters)
        page_query = (
            page_query.order_by(func.similarity(name_expr, query_text).desc())
            if query_text
            else page_query.order_by(User.created_at.desc())
        )
        page_result = await self._session.execute(page_query.limit(limit).offset(offset))
        return [(row.User, row.StaffProfile) for row in page_result.all()], total
