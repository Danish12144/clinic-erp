"""Doctor Management business logic: Owner-driven doctor account
provisioning (invite -> accept-credentials), profile CRUD (Owner: any
doctor; Doctor: own record only), branch assignment, and
activate/deactivate lifecycle. See PRD-ARCHITECTURE.md §3 (permission
matrix row "Doctor profile management"), §5 (staff invite workflow).

Reuses `staff.manage` (Owner) and `doctor.manage_own_profile` (Doctor) —
both already seeded in migration 0001 for exactly this capability row; no
new permission was needed. Invite issuance/acceptance is Auth's
`issue_staff_invite`/`AuthService.accept_invite` (see that module) — not
duplicated here.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.auth.models import UserStatus
from app.modules.auth.schemas import InviteInfo
from app.modules.auth.service import issue_staff_invite
from app.modules.doctors.models import DoctorProfile
from app.modules.doctors.repository import BranchAssignmentRepository, DoctorRepository
from app.modules.doctors.schemas import (
    DoctorCreateRequest,
    DoctorCreateResponse,
    DoctorDirectoryEntry,
    DoctorDirectoryResponse,
    DoctorListResponse,
    DoctorSummary,
    DoctorUpdateRequest,
)
from app.modules.tenancy.repository import BranchRepository


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

    async def create_doctor(
        self, *, tenant_id: uuid.UUID, payload: DoctorCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorCreateResponse:
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
                await BranchAssignmentRepository(session).set_branch_assignments(
                    tenant_id=tenant_id, user_id=user.id, branch_ids=payload.branch_ids
                )

            invite = await issue_staff_invite(session, tenant_id=tenant_id, user_id=user.id)
            summary = _to_summary(user, profile, payload.branch_ids)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="doctor.create",
                entity_type="doctor",
                entity_id=user.id,
                before=None,
                after=summary.model_dump(mode="json"),
            )
            return DoctorCreateResponse(doctor=summary, invite=invite)

    async def resend_invite(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> InviteInfo:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            user, _ = found
            if user.status != UserStatus.INVITED:
                raise HTTPException(status.HTTP_409_CONFLICT, "This account already has credentials set")
            return await issue_staff_invite(session, tenant_id=tenant_id, user_id=user_id)

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
            branch_repo = BranchAssignmentRepository(session)
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
                branch_ids = await branch_repo.get_branch_ids(user.id)
                items.append(_to_summary(user, profile, branch_ids))
            return DoctorListResponse(items=items, total=total, limit=limit, offset=offset)

    async def list_directory(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str | None,
        specialization: str | None,
        branch_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> DoctorDirectoryResponse:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            branch_repo = BranchAssignmentRepository(session)
            rows, total = await repo.search_directory(
                tenant_id=tenant_id,
                query_text=query_text,
                specialization=specialization,
                branch_id=branch_id,
                limit=limit,
                offset=offset,
            )
            items = []
            for user, profile in rows:
                branch_ids = await branch_repo.get_branch_ids(user.id)
                items.append(
                    DoctorDirectoryEntry(
                        user_id=user.id,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        specialization=profile.specialization,
                        consultation_fee=profile.consultation_fee,
                        working_hours=profile.working_hours,
                        branch_ids=branch_ids,
                    )
                )
            return DoctorDirectoryResponse(items=items, total=total, limit=limit, offset=offset)

    async def get_doctor(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
            user, profile = found
            branch_ids = await BranchAssignmentRepository(session).get_branch_ids(user_id)
            return _to_summary(user, profile, branch_ids)

    async def get_my_profile(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> DoctorSummary:
        return await self.get_doctor(tenant_id=tenant_id, user_id=user_id)

    async def _apply_update(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: DoctorUpdateRequest,
        actor_user_id: uuid.UUID,
        actor_role: str,
        action: str,
    ) -> DoctorSummary:
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
                action=action,
                entity_type="doctor",
                entity_id=user_id,
                before=before.model_dump(mode="json"),
                after=after.model_dump(mode="json"),
            )
            return after

    async def update_doctor(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: DoctorUpdateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        return await self._apply_update(
            tenant_id=tenant_id, user_id=user_id, payload=payload, actor_user_id=actor_user_id, actor_role=actor_role,
            action="doctor.update",
        )

    async def update_my_profile(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, payload: DoctorUpdateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        return await self._apply_update(
            tenant_id=tenant_id, user_id=user_id, payload=payload, actor_user_id=actor_user_id, actor_role=actor_role,
            action="doctor.update_own_profile",
        )

    async def _set_status(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, new_status: UserStatus, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
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
                action="doctor.deactivate" if new_status == UserStatus.INACTIVE else "doctor.reactivate",
                entity_type="doctor",
                entity_id=user_id,
                before={"status": previous_status},
                after={"status": new_status.value},
            )
            return _to_summary(updated[0], updated[1], branch_ids)

    async def deactivate_doctor(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        return await self._set_status(
            tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.INACTIVE, actor_user_id=actor_user_id, actor_role=actor_role
        )

    async def reactivate_doctor(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        return await self._set_status(
            tenant_id=tenant_id, user_id=user_id, new_status=UserStatus.ACTIVE, actor_user_id=actor_user_id, actor_role=actor_role
        )

    async def set_branches(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_ids: list[uuid.UUID], actor_user_id: uuid.UUID, actor_role: str
    ) -> DoctorSummary:
        async with tenant_session(tenant_id) as session:
            repo = DoctorRepository(session)
            found = await repo.get_user_and_profile(user_id)
            if found is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")
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
                action="doctor.branches.update",
                entity_type="doctor",
                entity_id=user_id,
                before={"branch_ids": [str(b) for b in previous_branch_ids]},
                after={"branch_ids": [str(b) for b in branch_ids]},
            )
            return _to_summary(updated[0], updated[1], branch_ids)
