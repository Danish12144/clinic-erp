"""API surface for the Tenancy module. Two route groups per
PRD-ARCHITECTURE.md §8: `/api/v1/clinics/*` and `/api/v1/branches/*`.

Read access to branches is open to any authenticated staff member (no
specific permission) — every role needs to know which branches exist
(scheduling, check-in, reporting). Clinic settings (profile + the
tenant_settings bag) and all writes are gated behind `clinic.manage_settings`
/ `branches.manage`, which the seed data grants to OWNER only (PRD §3).
"""

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.modules.tenancy.schemas import (
    BranchCreateRequest,
    BranchSummary,
    BranchUpdateRequest,
    ClinicSummary,
    ClinicUpdateRequest,
    TenantSettingSummary,
    TenantSettingUpsertRequest,
    validate_setting_key,
)
from app.modules.tenancy.service import TenancyService

clinic_router = APIRouter(prefix="/api/v1/clinics", tags=["tenancy:clinic"])
branch_router = APIRouter(prefix="/api/v1/branches", tags=["tenancy:branches"])


def get_tenancy_service() -> TenancyService:
    return TenancyService()


# ---- Clinic profile ----------------------------------------------------------


@clinic_router.get("/me", response_model=ClinicSummary)
async def get_my_clinic(
    current_user: CurrentUser = Depends(get_current_user), service: TenancyService = Depends(get_tenancy_service)
) -> ClinicSummary:
    return await service.get_clinic(tenant_id=current_user.tenant_id)


@clinic_router.patch("/me", response_model=ClinicSummary)
async def update_my_clinic(
    payload: ClinicUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: TenancyService = Depends(get_tenancy_service),
) -> ClinicSummary:
    return await service.update_clinic(tenant_id=current_user.tenant_id, payload=payload)


# ---- Clinic settings bag -----------------------------------------------------


@clinic_router.get("/me/settings", response_model=list[TenantSettingSummary])
async def list_clinic_settings(
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: TenancyService = Depends(get_tenancy_service),
) -> list[TenantSettingSummary]:
    return await service.list_settings(tenant_id=current_user.tenant_id)


@clinic_router.get("/me/settings/{key}", response_model=TenantSettingSummary)
async def get_clinic_setting(
    key: str,
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: TenancyService = Depends(get_tenancy_service),
) -> TenantSettingSummary:
    validate_setting_key_or_422(key)
    return await service.get_setting(tenant_id=current_user.tenant_id, key=key)


@clinic_router.put("/me/settings/{key}", response_model=TenantSettingSummary)
async def upsert_clinic_setting(
    key: str,
    payload: TenantSettingUpsertRequest = Body(...),
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: TenancyService = Depends(get_tenancy_service),
) -> TenantSettingSummary:
    validate_setting_key_or_422(key)
    return await service.upsert_setting(tenant_id=current_user.tenant_id, key=key, value=payload.value)


@clinic_router.delete("/me/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clinic_setting(
    key: str,
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: TenancyService = Depends(get_tenancy_service),
) -> None:
    validate_setting_key_or_422(key)
    await service.delete_setting(tenant_id=current_user.tenant_id, key=key)


def validate_setting_key_or_422(key: str) -> None:
    """`key` is a path parameter, so Pydantic's normal field-validator
    machinery doesn't run on it automatically — validate manually and
    raise the same 422 a body validation failure would produce (a bare
    pydantic.ValidationError here would NOT be caught by FastAPI's default
    handlers and would surface as a 500, so HTTPException is deliberate)."""
    try:
        validate_setting_key(key)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


# ---- Branches -----------------------------------------------------------------


@branch_router.post("", response_model=BranchSummary, status_code=status.HTTP_201_CREATED)
async def create_branch(
    payload: BranchCreateRequest,
    current_user: CurrentUser = Depends(require_permission("branches.manage")),
    service: TenancyService = Depends(get_tenancy_service),
) -> BranchSummary:
    return await service.create_branch(tenant_id=current_user.tenant_id, payload=payload)


@branch_router.get("", response_model=list[BranchSummary])
async def list_branches(
    include_inactive: bool = Query(True),
    current_user: CurrentUser = Depends(get_current_user),
    service: TenancyService = Depends(get_tenancy_service),
) -> list[BranchSummary]:
    return await service.list_branches(tenant_id=current_user.tenant_id, include_inactive=include_inactive)


@branch_router.get("/{branch_id}", response_model=BranchSummary)
async def get_branch(
    branch_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: TenancyService = Depends(get_tenancy_service),
) -> BranchSummary:
    return await service.get_branch(tenant_id=current_user.tenant_id, branch_id=branch_id)


@branch_router.patch("/{branch_id}", response_model=BranchSummary)
async def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("branches.manage")),
    service: TenancyService = Depends(get_tenancy_service),
) -> BranchSummary:
    return await service.update_branch(tenant_id=current_user.tenant_id, branch_id=branch_id, payload=payload)
