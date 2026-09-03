"""Doctor Management business logic: Owner-driven doctor account
provisioning (invite -> accept-credentials), profile CRUD (Owner: any
doctor; Doctor: own record only), branch assignment, and
activate/deactivate lifecycle. See PRD-ARCHITECTURE.md §3 (permission
matrix row "Doctor profile management"), §5 (staff invite workflow).

Reuses `staff.manage` (Owner) and `doctor.manage_own_profile` (Doctor) —
both already seeded in migration 0001 for exactly this capability row; no
new permission was needed.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.auth.models import UserStatus
from app.modules.auth.repository import TenantResolutionRepository
from app.modules.doctors.models import DoctorProfile
from app.modules.doctors.repository import DoctorRepository, StaffInviteRepository
from app.modules.doctors.schemas import (
    AcceptInviteResponse,
    DoctorCreateRequest,
    DoctorCreateResponse,
    DoctorListResponse,
    DoctorSummary,
    DoctorUpdateRequest,
    InviteInfo,
)
from app.modules.tenancy.repository import BranchRepository

settings = get_settings()


def _to_summary(user, profile: DoctorProfile, branch_ids: list[uuid.UUID]) -> DoctorSummary:
    return DoctorSummary(
        user_id=user.id,
        tenant_id=user.tenant_id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        status=user.status.value,
        specialization=profile.specialization,
        registration_number=profile.registration_number,
        consultation_fee=profile.consultation_fee,
        working_hours=profile.working_hours,
        bio=profile.bio,
        branch_ids=branch_ids,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


class DoctorService:
    async def _validate_branch_ids(self, session, branch_ids: list[uuid.UUID]) -> None:
        branch_repo = BranchRepository(session)
        for branch_id in branch_ids:
            if await branch_repo.get_by_id(branch_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{branch_id}' does not exist")

    async def create_doctor(self, *, tenant_id: uuid.UUID, payload: DoctorCreateRequest) -> DoctorCreateResponse:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            await self._validate_branch_ids(session, payload.branch_ids)

            role_id = await repo.get_role_id("DOCTOR")
            try:
                user = await repo.create_user(
                    tenant_id=tenant_id,
                    role_id=role_id,
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                    email=payload.email,
                    phone=payload.phone,
                )
            except IntegrityError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, "A staff account with that email or phone already exists"
                ) from exc

            profile = await repo.create_profile(
                user_id=user.id,
                tenant_id=tenant_id,
                specialization=payload.specialization,
                registration_number=payload.registration_number,
                consultation_fee=payload.consultation_fee,
                working_hours=payload.working_hours.model_dump(exclude_none=True),
                bio=payload.bio,
            )

            if payload.branch_ids:
                await repo.set_branch_assignments(tenant_id=tenant_id, user_id=user.id, branch_ids=payload.branch_ids)

            invite = await self._issue_invite(session, tenant_id=tenant_id, user_id=user.id)
            return DoctorCreateResponse(doctor=_to_summary(user, profile, payload.branch_ids), invite=invite)

    async def _issue_invite(self, session, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
        invite_repo = StaffInviteRepository(session)
        await invite_repo.delete_pending_for_user(user_id)
        token = security.generate_opaque_token()
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.staff_invite_expire_hours)
        await invite_repo.create(
            tenant_id=tenant_id, user_id=user_id, token_hash=security.hash_opaque_token(token), expires_at=expires_at
        )
        return InviteInfo(invite_expires_at=expires_at, debug_invite_token=None if settings.is_production else token)

    async def resend_invite(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            user, _ = found
            if user.status != UserStatus.INVITED:
                raise HTTPException(status.HTTP_409_CONFLICT, "This account already has credentials set")
            return await self._issue_invite(session, tenant_id=tenant_id, user_id=user_id)

    async def accept_invite(self, *, clinic_slug: str, token: str, password: str) -> AcceptInviteResponse:
        clinic = await TenantResolutionRepository.get_active_clinic_by_slug(clinic_slug)
        invalid_error = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired invite")
        if clinic is None:
            raise invalid_error

        async with tenant_session(clinic.id) as session:
            invite_repo = StaffInviteRepository(session)
            invite = await invite_repo.get_active_by_token_hash(security.hash_opaque_token(token))
            if invite is None or invite.expires_at < datetime.now(timezone.utc):
                raise invalid_error

            repo = DoctorRepository(session)
            await repo.update_user(invite.user_id, password_hash=security.hash_password(password), status=UserStatus.ACTIVE)
            await invite_repo.mark_accepted(invite.id)
            return AcceptInviteResponse(message="Invite accepted — you can now log in with your new password")

    async def search_doctors(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str | None,
        specialization: str | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> DoctorListResponse:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            rows, total = await repo.search(
                tenant_id=tenant_id,
                query_text=query_text,
                specialization=specialization,
                include_inactive=include_inactive,
                limit=limit,
                offset=offset,
            )
            items = []
            for user, profile in rows:
                branch_ids = await repo.get_branch_ids(user.id)
                items.append(_to_summary(user, profile, branch_ids))
            return DoctorListResponse(items=items, total=total, limit=limit, offset=offset)

    async def get_doctor(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            user, profile = found
            branch_ids = await repo.get_branch_ids(user_id)
            return _to_summary(user, profile, branch_ids)

    async def get_my_profile(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        return await self.get_doctor(tenant_id=tenant_id, user_id=user_id)

    async def _apply_update(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: DoctorUpdateRequest) -> DoctorSummary:
        changes = payload.model_dump(exclude_unset=True, exclude={"first_name", "last_name", "working_hours"})
        if "working_hours" in payload.model_fields_set:
            changes["working_hours"] = payload.working_hours.model_dump(exclude_none=True) if payload.working_hours else {}

        user_changes = {}
        for field in ("first_name", "last_name"):
            if field in payload.model_fields_set:
                user_changes[field] = getattr(payload, field)

        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            await repo.update_profile(user_id, **changes)
            await repo.update_user(user_id, **user_changes)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            branch_ids = await repo.get_branch_ids(user_id)
            return _to_summary(updated[0], updated[1], branch_ids)

    async def update_doctor(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: DoctorUpdateRequest) -> DoctorSummary:
        return await self._apply_update(tenant_id=tenant_id, user_id=user_id, payload=payload)

    async def update_my_profile(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: DoctorUpdateRequest) -> DoctorSummary:
        return await self._apply_update(tenant_id=tenant_id, user_id=user_id, payload=payload)

    async def _set_status(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, new_status: UserStatus) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            await repo.update_user(user_id, status=new_status)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            branch_ids = await repo.get_branch_ids(user_id)
            return _to_summary(updated[0], updated[1], branch_ids)

    async def deactivate_doctor(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        return await self._set_status(tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.INACTIVE)

    async def reactivate_doctor(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        return await self._set_status(tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.ACTIVE)

    async def set_branches(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_ids: list[uuid.UUID]) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            await self._validate_branch_ids(session, branch_ids)
            await repo.set_branch_assignments(tenant_id=tenant_id, user_id=user_id, branch_ids=branch_ids)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            return _to_summary(updated[0], updated[1], branch_ids)
