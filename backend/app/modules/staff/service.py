"""Staff Management business logic: Owner-driven provisioning (invite ->
accept-credentials, same mechanism Doctor Management uses) for non-doctor
staff roles, profile CRUD, branch assignment, and activate/deactivate
lifecycle. See PRD-ARCHITECTURE.md §3 (permission matrix row "Staff, roles
& permissions" — Owner F, everyone else –).

Unlike Doctor Management, there is no self-service "/me" here: the PRD
matrix gives no role other than Owner any access to this capability, not
even "own record" — a Receptionist's basic identity is already visible via
the existing generic `GET /api/v1/auth/me` (Auth module); the
`employee_code`/`designation`/`joining_date` extension fields are
Owner-only administrative data.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.auth.models import UserStatus
from app.modules.auth.schemas import InviteInfo
from app.modules.auth.service import issue_staff_invite

settings = get_settings()
from app.modules.doctors.repository import BranchAssignmentRepository
from app.modules.staff.models import StaffProfile
from app.modules.staff.repository import StaffRepository
from app.modules.staff.schemas import StaffCreateRequest, StaffCreateResponse, StaffListResponse, StaffSummary, StaffUpdateRequest
from app.modules.tenancy.repository import BranchRepository


def _to_summary(user, profile: StaffProfile, branch_ids: list[uuid.UUID]) -> StaffSummary:
    return StaffSummary(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role_code=user.role.code,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        status=user.status.value,
        employee_code=profile.employee_code,
        designation=profile.designation,
        joining_date=profile.joining_date,
        branch_ids=branch_ids,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


class StaffService:
    async def _validate_branch_ids(self, session, branch_ids: list[uuid.UUID]) -> None:
        branch_repo = BranchRepository(session)
        for branch_id in branch_ids:
            if await branch_repo.get_by_id(branch_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{branch_id}' does not exist")

    async def create_staff(
        self, *, tenant_id: uuid.UUID, payload: StaffCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffCreateResponse:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            await self._validate_branch_ids(session, payload.branch_ids)

            role_id = await repo.get_role_id(payload.role_code)
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
                employee_code=payload.employee_code,
                designation=payload.designation,
                joining_date=payload.joining_date,
            )

            if payload.branch_ids:
                await BranchAssignmentRepository(session).set_branch_assignments(
                    tenant_id=tenant_id, user_id=user.id, branch_ids=payload.branch_ids
                )

            invite = await issue_staff_invite(session, tenant_id=tenant_id, user_id=user.id)
            # user.role isn't populated on a just-constructed instance the
            # way a fresh SELECT's joined-load would — payload.role_code is
            # already the validated, authoritative value for this response.
            summary = StaffSummary(
                user_id=user.id,
                tenant_id=user.tenant_id,
                role_code=payload.role_code,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone=user.phone,
                status=user.status.value,
                employee_code=profile.employee_code,
                designation=profile.designation,
                joining_date=profile.joining_date,
                branch_ids=payload.branch_ids,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="staff.create",
                entity_type="staff",
                entity_id=user.id,
                before=None,
                after=summary.model_dump(mode="json"),
            )
            return StaffCreateResponse(staff=summary, invite=invite)

    async def resend_invite(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
            user, _ = found
            # In production, issue_staff_invite always (re)generates a
            # temporary password rather than a token — there's no more
            # INVITED-only window to gate on, since create_staff already
            # activates the account immediately there. Outside production
            # the real invite/accept-invite flow is unchanged, so this
            # precondition still applies exactly as before.
            if not settings.is_production and user.status != UserStatus.INVITED:
                raise HTTPException(status.HTTP_409_CONFLICT, "This account already has credentials set")
            return await issue_staff_invite(session, tenant_id=tenant_id, user_id=user_id)

    async def search_staff(
        self,
        *,
        tenant_id: uuid.UUID,
        role_code: str | None,
        query_text: str | None,
        include_inactive: bool,
        limit: int,
        offset: int,
    ) -> StaffListResponse:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            branch_repo = BranchAssignmentRepository(session)
            rows, total = await repo.search(
                tenant_id=tenant_id,
                role_code=role_code,
                query_text=query_text,
                include_inactive=include_inactive,
                limit=limit,
                offset=offset,
            )
            items = []
            for user, profile in rows:
                branch_ids = await branch_repo.get_branch_ids(user.id)
                items.append(_to_summary(user, profile, branch_ids))
            return StaffListResponse(items=items, total=total, limit=limit, offset=offset)

    async def get_staff(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> StaffSummary:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
            user, profile = found
            branch_ids = await BranchAssignmentRepository(session).get_branch_ids(user_id)
            return _to_summary(user, profile, branch_ids)

    async def update_staff(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: StaffUpdateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffSummary:
        changes = payload.model_dump(exclude_unset=True, exclude={"first_name", "last_name"})
        user_changes = {}
        for field in ("first_name", "last_name"):
            if field in payload.model_fields_set:
                user_changes[field] = getattr(payload, field)

        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
            branch_ids = await BranchAssignmentRepository(session).get_branch_ids(user_id)
            before = _to_summary(found[0], found[1], branch_ids)
            await repo.update_profile(user_id, **changes)
            await repo.update_user(user_id, **user_changes)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            after = _to_summary(updated[0], updated[1], branch_ids)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="staff.update",
                entity_type="staff",
                entity_id=user_id,
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )
            return after

    async def _set_status(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, new_status: UserStatus, actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffSummary:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
            previous_status = found[0].status.value
            await repo.update_user(user_id, status=new_status)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            branch_ids = await BranchAssignmentRepository(session).get_branch_ids(user_id)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="staff.deactivate" if new_status == UserStatus.INACTIVE else "staff.reactivate",
                entity_type="staff",
                entity_id=user_id,
                before={"status": previous_status},
                after={"status": new_status.value},
            )
            return _to_summary(updated[0], updated[1], branch_ids)

    async def deactivate_staff(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffSummary:
        return await self._set_status(
            tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.INACTIVE, actor_user_id=actor_user_id, actor_role=actor_role
        )

    async def reactivate_staff(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffSummary:
        return await self._set_status(
            tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.ACTIVE, actor_user_id=actor_user_id, actor_role=actor_role
        )

    async def set_branches(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_ids: list[uuid.UUID], actor_user_id: uuid.UUID, actor_role: str
    ) -> StaffSummary:
        async with tenant_session(tenant_id) as session:
            repo = StaffRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
            await self._validate_branch_ids(session, branch_ids)
            branch_repo = BranchAssignmentRepository(session)
            previous_branch_ids = await branch_repo.get_branch_ids(user_id)
            await branch_repo.set_branch_assignments(tenant_id=tenant_id, user_id=user_id, branch_ids=branch_ids)
            updated = await repo.get_user_and_profile(user_id)
            assert updated is not None
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="staff.branches.update",
                entity_type="staff",
                entity_id=user_id,
                before={"branch_ids": [str(b) for b in previous_branch_ids]},
                after={"branch_ids": [str(b) for b in branch_ids]},
            )
            return _to_summary(updated[0], updated[1], branch_ids)
