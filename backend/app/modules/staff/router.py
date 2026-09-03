"""API surface for the Staff Management module —
PRD-ARCHITECTURE.md §8: `/api/v1/staff/*`.

Per the PRD §3 matrix ("Staff, roles & permissions": Owner F, everyone
else –), every route here is Owner-only (`staff.manage`) — unlike Doctor
Management there is no self-service "/me" (see the module docstring in
app/modules/staff/service.py for why). Accepting the invite this module
issues happens at `POST /api/v1/auth/accept-invite` (Auth module).
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.auth.schemas import InviteInfo
from app.modules.staff.schemas import (
    BranchAssignmentRequest,
    StaffCreateRequest,
    StaffCreateResponse,
    StaffListResponse,
    StaffSummary,
    StaffUpdateRequest,
)
from app.modules.staff.service import StaffService

router = APIRouter(prefix="/api/v1/staff", tags=["staff"])


def get_staff_service() -> StaffService:
    return StaffService()


@router.post("", response_model=StaffCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreateRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffCreateResponse:
    return await service.create_staff(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@router.get("", response_model=StaffListResponse)
async def search_staff(
    q: str | None = Query(None, description="Fuzzy match against staff name"),
    role_code: str | None = Query(None),
    include_inactive: bool = Query(False, description="Include deactivated staff (invited-but-not-yet-active ones are always included)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffListResponse:
    return await service.search_staff(
        tenant_id=current_user.tenant_id,
        role_code=role_code,
        query_text=q,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=StaffSummary)
async def get_staff(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffSummary:
    return await service.get_staff(tenant_id=current_user.tenant_id, user_id=user_id)


@router.patch("/{user_id}", response_model=StaffSummary)
async def update_staff(
    user_id: uuid.UUID,
    payload: StaffUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffSummary:
    return await service.update_staff(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        payload=payload,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )


@router.post("/{user_id}/deactivate", response_model=StaffSummary)
async def deactivate_staff(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffSummary:
    return await service.deactivate_staff(
        tenant_id=current_user.tenant_id, user_id=user_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@router.post("/{user_id}/reactivate", response_model=StaffSummary)
async def reactivate_staff(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffSummary:
    return await service.reactivate_staff(
        tenant_id=current_user.tenant_id, user_id=user_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@router.put("/{user_id}/branches", response_model=StaffSummary)
async def set_staff_branches(
    user_id: uuid.UUID,
    payload: BranchAssignmentRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> StaffSummary:
    return await service.set_branches(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        branch_ids=payload.branch_ids,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )


@router.post("/{user_id}/invite/resend", response_model=InviteInfo)
async def resend_invite(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: StaffService = Depends(get_staff_service),
) -> InviteInfo:
    return await service.resend_invite(tenant_id=current_user.tenant_id, user_id=user_id)
