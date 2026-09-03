"""API surface for the Doctor Management module —
PRD-ARCHITECTURE.md §8: `/api/v1/doctors/*`.

Per the PRD §3 matrix ("Doctor profile management": Owner F, Doctor O,
everyone else –), listing/creating/managing any doctor is Owner-only
(`staff.manage`); a Doctor may only view/update their own record
(`doctor.manage_own_profile`), via the `/me` routes. `/accept-invite` is
the one unauthenticated route — a newly invited doctor has no credentials
yet.

Static-path routes (`/me`, `/accept-invite`) are declared before the
`/{user_id}` routes so FastAPI matches them first — `user_id` is typed as
a UUID path param and would 422 on "me"/"accept-invite" if a param route
were matched first.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.modules.doctors.schemas import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    BranchAssignmentRequest,
    DoctorCreateRequest,
    DoctorCreateResponse,
    DoctorListResponse,
    DoctorSummary,
    DoctorUpdateRequest,
    InviteInfo,
)
from app.modules.doctors.service import DoctorService

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])


def get_doctor_service() -> DoctorService:
    return DoctorService()


@router.post("", response_model=DoctorCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_doctor(
    payload: DoctorCreateRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorCreateResponse:
    return await service.create_doctor(tenant_id=current_user.tenant_id, payload=payload)


@router.get("", response_model=DoctorListResponse)
async def search_doctors(
    q: str | None = Query(None, description="Fuzzy match against doctor name"),
    specialization: str | None = Query(None),
    include_inactive: bool = Query(False, description="Include deactivated doctors (invited-but-not-yet-active ones are always included)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorListResponse:
    return await service.search_doctors(
        tenant_id=current_user.tenant_id,
        query_text=q,
        specialization=specialization,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )


@router.post("/accept-invite", response_model=AcceptInviteResponse)
async def accept_invite(
    payload: AcceptInviteRequest, service: DoctorService = Depends(get_doctor_service)
) -> AcceptInviteResponse:
    return await service.accept_invite(clinic_slug=payload.clinic_slug, token=payload.token, password=payload.password)


@router.get("/me", response_model=DoctorSummary)
async def get_my_profile(
    current_user: CurrentUser = Depends(get_current_user), service: DoctorService = Depends(get_doctor_service)
) -> DoctorSummary:
    return await service.get_my_profile(tenant_id=current_user.tenant_id, user_id=current_user.user_id)


@router.patch("/me", response_model=DoctorSummary)
async def update_my_profile(
    payload: DoctorUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("doctor.manage_own_profile")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.update_my_profile(tenant_id=current_user.tenant_id, user_id=current_user.user_id, payload=payload)


@router.get("/{user_id}", response_model=DoctorSummary)
async def get_doctor(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.get_doctor(tenant_id=current_user.tenant_id, user_id=user_id)


@router.patch("/{user_id}", response_model=DoctorSummary)
async def update_doctor(
    user_id: uuid.UUID,
    payload: DoctorUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.update_doctor(tenant_id=current_user.tenant_id, user_id=user_id, payload=payload)


@router.post("/{user_id}/deactivate", response_model=DoctorSummary)
async def deactivate_doctor(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.deactivate_doctor(tenant_id=current_user.tenant_id, user_id=user_id)


@router.post("/{user_id}/reactivate", response_model=DoctorSummary)
async def reactivate_doctor(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.reactivate_doctor(tenant_id=current_user.tenant_id, user_id=user_id)


@router.put("/{user_id}/branches", response_model=DoctorSummary)
async def set_doctor_branches(
    user_id: uuid.UUID,
    payload: BranchAssignmentRequest,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> DoctorSummary:
    return await service.set_branches(tenant_id=current_user.tenant_id, user_id=user_id, branch_ids=payload.branch_ids)


@router.post("/{user_id}/invite/resend", response_model=InviteInfo)
async def resend_invite(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("staff.manage")),
    service: DoctorService = Depends(get_doctor_service),
) -> InviteInfo:
    return await service.resend_invite(tenant_id=current_user.tenant_id, user_id=user_id)
