"""API surface for CRM & Follow-ups — PRD-ARCHITECTURE.md §8:
`/api/v1/crm/follow-ups/*`.

`crm.manage` gates every route here — Owner/Receptionist unscoped
(matches the PRD §3 matrix's "F" on "CRM, leads, follow-ups"), Doctor
row-scoped to `doctor_id == self` at the service layer (a deliberate
matrix deviation — the matrix gives Doctor "–" — by direct instruction;
see migration 0019's docstring).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.crm.models import FollowUpStatus
from app.modules.crm.schemas import (
    FollowUpCreateRequest,
    FollowUpListResponse,
    FollowUpStatusUpdateRequest,
    FollowUpSummary,
)
from app.modules.crm.service import FollowUpService

router = APIRouter(prefix="/api/v1/crm/follow-ups", tags=["crm"])


def get_follow_up_service() -> FollowUpService:
    return FollowUpService()


@router.post("", response_model=FollowUpSummary, status_code=status.HTTP_201_CREATED)
async def create_follow_up(
    payload: FollowUpCreateRequest,
    current_user: CurrentUser = Depends(require_permission("crm.manage")),
    service: FollowUpService = Depends(get_follow_up_service),
) -> FollowUpSummary:
    return await service.create_follow_up(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@router.get("", response_model=FollowUpListResponse)
async def search_follow_ups(
    patient_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    status_filter: FollowUpStatus | None = Query(None, alias="status"),
    due_from: datetime | None = Query(None),
    due_to: datetime | None = Query(None),
    overdue: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("crm.manage")),
    service: FollowUpService = Depends(get_follow_up_service),
) -> FollowUpListResponse:
    return await service.search_follow_ups(
        tenant_id=current_user.tenant_id, patient_id=patient_id, doctor_id=doctor_id, status_filter=status_filter,
        due_from=due_from, due_to=due_to, overdue_only=overdue, actor_role=current_user.role_code, actor_user_id=current_user.user_id,
        limit=limit, offset=offset,
    )


@router.get("/{follow_up_id}", response_model=FollowUpSummary)
async def get_follow_up(
    follow_up_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("crm.manage")),
    service: FollowUpService = Depends(get_follow_up_service),
) -> FollowUpSummary:
    return await service.get_follow_up(tenant_id=current_user.tenant_id, follow_up_id=follow_up_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id)


@router.patch("/{follow_up_id}/status", response_model=FollowUpSummary)
async def update_follow_up_status(
    follow_up_id: uuid.UUID,
    payload: FollowUpStatusUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("crm.manage")),
    service: FollowUpService = Depends(get_follow_up_service),
) -> FollowUpSummary:
    return await service.update_status(tenant_id=current_user.tenant_id, follow_up_id=follow_up_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
