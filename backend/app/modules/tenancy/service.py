"""Tenancy module business logic: clinic profile/settings management and
branch CRUD, both scoped to the caller's own tenant. See
PRD-ARCHITECTURE.md §4 (tenancy strategy), §22 (multi-branch).

Every method takes `tenant_id` explicitly (from the caller's JWT via
app/api/deps.py::CurrentUser) and opens its own tenant-scoped session —
same pattern as app/modules/auth/service.py. Nothing here ever needs the
Platform Admin bypass: a clinic managing its own settings/branches is
exactly the case tenant_session's RLS scoping is designed for.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.tenancy.repository import BranchRepository, ClinicRepository, TenantSettingRepository
from app.modules.tenancy.schemas import (
    BranchCreateRequest,
    BranchSummary,
    BranchUpdateRequest,
    ClinicSummary,
    ClinicUpdateRequest,
    TenantSettingSummary,
)


class TenancyService:
    # ---- Clinic profile & settings --------------------------------------

    async def get_clinic(self, *, tenant_id: uuid.UUID) -> ClinicSummary:
        async with tenant_session(tenant_id) as session:
            clinic = await ClinicRepository(session).get_by_id(tenant_id)
            if clinic is None:
                # Should be unreachable — a valid JWT implies the clinic
                # existed at token issuance — but a clinic could in theory
                # be removed between issuance and this call.
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
            return ClinicSummary.model_validate(clinic)

    async def update_clinic(self, *, tenant_id: uuid.UUID, payload: ClinicUpdateRequest) -> ClinicSummary:
        changes = payload.model_dump(exclude_unset=True)
        async with tenant_session(tenant_id) as session:
            repo = ClinicRepository(session)
            clinic = await repo.get_by_id(tenant_id)
            if clinic is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Clinic not found")
            await repo.update(tenant_id, **changes)
            updated = await repo.get_by_id(tenant_id)
            return ClinicSummary.model_validate(updated)

    async def list_settings(self, *, tenant_id: uuid.UUID) -> list[TenantSettingSummary]:
        async with tenant_session(tenant_id) as session:
            settings = await TenantSettingRepository(session).list_all(tenant_id=tenant_id)
            return [TenantSettingSummary.model_validate(s) for s in settings]

    async def get_setting(self, *, tenant_id: uuid.UUID, key: str) -> TenantSettingSummary:
        async with tenant_session(tenant_id) as session:
            setting = await TenantSettingRepository(session).get_by_key(tenant_id=tenant_id, key=key)
            if setting is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Setting not found")
            return TenantSettingSummary.model_validate(setting)

    async def upsert_setting(self, *, tenant_id: uuid.UUID, key: str, value: object) -> TenantSettingSummary:
        async with tenant_session(tenant_id) as session:
            setting = await TenantSettingRepository(session).upsert(tenant_id=tenant_id, key=key, value=value)
            return TenantSettingSummary.model_validate(setting)

    async def delete_setting(self, *, tenant_id: uuid.UUID, key: str) -> None:
        async with tenant_session(tenant_id) as session:
            deleted = await TenantSettingRepository(session).delete(tenant_id=tenant_id, key=key)
            if not deleted:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Setting not found")

    # ---- Branches ----------------------------------------------------------

    async def create_branch(self, *, tenant_id: uuid.UUID, payload: BranchCreateRequest) -> BranchSummary:
        async with tenant_session(tenant_id) as session:
            repo = BranchRepository(session)
            try:
                branch = await repo.create(
                    tenant_id=tenant_id,
                    name=payload.name,
                    address=payload.address,
                    phone=payload.phone,
                    timezone_=payload.timezone,
                    working_hours=payload.working_hours.model_dump(exclude_none=True),
                )
            except IntegrityError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"A branch named '{payload.name}' already exists"
                ) from exc
            return BranchSummary.model_validate(branch)

    async def list_branches(self, *, tenant_id: uuid.UUID, include_inactive: bool = True) -> list[BranchSummary]:
        async with tenant_session(tenant_id) as session:
            branches = await BranchRepository(session).list_all(include_inactive=include_inactive)
            return [BranchSummary.model_validate(b) for b in branches]

    async def get_branch(self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> BranchSummary:
        async with tenant_session(tenant_id) as session:
            branch = await BranchRepository(session).get_by_id(branch_id)
            if branch is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
            return BranchSummary.model_validate(branch)

    async def update_branch(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID, payload: BranchUpdateRequest
    ) -> BranchSummary:
        changes = payload.model_dump(exclude_unset=True, exclude={"working_hours"})
        if "working_hours" in payload.model_fields_set:
            changes["working_hours"] = payload.working_hours.model_dump(exclude_none=True) if payload.working_hours else {}

        async with tenant_session(tenant_id) as session:
            repo = BranchRepository(session)
            branch = await repo.get_by_id(branch_id)
            if branch is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Branch not found")
            try:
                await repo.update(branch_id, **changes)
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "A branch with that name already exists") from exc
            updated = await repo.get_by_id(branch_id)
            return BranchSummary.model_validate(updated)
