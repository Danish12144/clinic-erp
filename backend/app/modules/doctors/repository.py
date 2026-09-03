import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import Role, User, UserStatus
from app.modules.doctors.models import DoctorProfile, UserBranchAssignment


class DoctorRepository:
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
        specialization: str | None,
        registration_number: str | None,
        consultation_fee,
        working_hours: dict,
        bio: str | None,
    ) -> DoctorProfile:
        profile = DoctorProfile(
            user_id=user_id,
            tenant_id=tenant_id,
            specialization=specialization,
            registration_number=registration_number,
            consultation_fee=consultation_fee,
            working_hours=working_hours,
            bio=bio,
        )
        self._session.add(profile)
        await self._session.flush()
        return profile

    async def get_user_and_profile(self, user_id: uuid.UUID) -> tuple[User, DoctorProfile] | None:
        user_result = await self._session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return None
        profile_result = await self._session.execute(select(DoctorProfile).where(DoctorProfile.user_id == user_id))
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
        await self._session.execute(update(DoctorProfile).where(DoctorProfile.user_id == user_id).values(**fields))

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str | None,
        specialization: str | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[User, DoctorProfile]], int]:
        filters = [User.tenant_id == tenant_id, DoctorProfile.user_id == User.id]
        if not include_inactive:
            # "inactive" here means deactivated (UserStatus.INACTIVE), not
            # "not yet accepted their invite" — a freshly invited doctor
            # (UserStatus.INVITED) should still show up in the default
            # search, so the Owner can see who they've invited.
            filters.append(User.status != UserStatus.INACTIVE)
        if specialization:
            filters.append(func.lower(DoctorProfile.specialization) == specialization.lower())
        name_expr = func.concat(User.first_name, " ", func.coalesce(User.last_name, ""))
        if query_text:
            # pg_trgm similarity (extension created in migration 0004),
            # tolerates typos the same way patient name search does.
            filters.append(func.similarity(name_expr, query_text) > 0.2)

        count_result = await self._session.execute(
            select(func.count()).select_from(User).join(DoctorProfile, DoctorProfile.user_id == User.id).where(*filters)
        )
        total = count_result.scalar_one()

        page_query = select(User, DoctorProfile).join(DoctorProfile, DoctorProfile.user_id == User.id).where(*filters)
        page_query = (
            page_query.order_by(func.similarity(name_expr, query_text).desc())
            if query_text
            else page_query.order_by(User.created_at.desc())
        )
        page_result = await self._session.execute(page_query.limit(limit).offset(offset))
        return [(row.User, row.DoctorProfile) for row in page_result.all()], total


class BranchAssignmentRepository:
    """Generic to any staff role, not doctor-specific — Staff Management
    reuses this directly rather than duplicating it. Lives here (not in
    Auth) because it's about branch scoping, not identity/credentials."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_branch_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        result = await self._session.execute(
            select(UserBranchAssignment.branch_id).where(UserBranchAssignment.user_id == user_id)
        )
        return list(result.scalars().all())

    async def set_branch_assignments(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_ids: list[uuid.UUID]) -> None:
        await self._session.execute(delete(UserBranchAssignment).where(UserBranchAssignment.user_id == user_id))
        for branch_id in branch_ids:
            self._session.add(UserBranchAssignment(tenant_id=tenant_id, user_id=user_id, branch_id=branch_id))
        await self._session.flush()
