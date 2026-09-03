"""API surface for walk-in registration, check-in, and queue/token
management — PRD-ARCHITECTURE.md §8: `/api/v1/encounters/*` (check-in,
encounter lifecycle) and `/api/v1/queue/*` (token issuance, call-next,
status transitions).

Per the PRD §3 matrix, both "Walk-in registration & check-in" and "Queue /
token management" give Owner/Receptionist full (F) access and Doctor/Nurse
read-only (R) — `checkin.manage`/`queue.manage` gate the write routes,
`checkin.view`/`queue.view` gate the read ones. Unlike Appointments'
"R (own)" for Doctor, neither row here is marked "(own)", so reads are
tenant/branch-wide for every role that has them — no row-level doctor
scoping in this module.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.checkin.models import EncounterStatus, QueueTokenStatus
from app.modules.checkin.schemas import (
    CheckInResult,
    EncounterCancelRequest,
    EncounterListResponse,
    EncounterSummary,
    QueueListResponse,
    QueueStatusUpdateRequest,
    QueueTokenSummary,
    WalkInRequest,
)
from app.modules.checkin.service import CheckInService

encounter_router = APIRouter(prefix="/api/v1/encounters", tags=["check-in"])
queue_router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


def get_checkin_service() -> CheckInService:
    return CheckInService()


# ---- Encounters (walk-in / check-in) --------------------------------------


@encounter_router.post("/walk-in", response_model=CheckInResult, status_code=status.HTTP_201_CREATED)
async def register_walk_in(
    payload: WalkInRequest,
    current_user: CurrentUser = Depends(require_permission("checkin.manage")),
    service: CheckInService = Depends(get_checkin_service),
) -> CheckInResult:
    return await service.register_walk_in(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@encounter_router.post("/{appointment_id}/check-in", response_model=CheckInResult, status_code=status.HTTP_201_CREATED)
async def check_in_appointment(
    appointment_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("checkin.manage")),
    service: CheckInService = Depends(get_checkin_service),
) -> CheckInResult:
    return await service.check_in_appointment(
        tenant_id=current_user.tenant_id, appointment_id=appointment_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@encounter_router.post("/{appointment_id}/no-show")
async def mark_no_show(
    appointment_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("checkin.manage")),
    service: CheckInService = Depends(get_checkin_service),
):
    return await service.mark_no_show(
        tenant_id=current_user.tenant_id, appointment_id=appointment_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@encounter_router.get("", response_model=EncounterListResponse)
async def search_encounters(
    branch_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    status_filter: EncounterStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("checkin.view")),
    service: CheckInService = Depends(get_checkin_service),
) -> EncounterListResponse:
    return await service.search_encounters(
        tenant_id=current_user.tenant_id,
        branch_id=branch_id,
        patient_id=patient_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@encounter_router.get("/{encounter_id}", response_model=EncounterSummary)
async def get_encounter(
    encounter_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("checkin.view")),
    service: CheckInService = Depends(get_checkin_service),
) -> EncounterSummary:
    return await service.get_encounter(tenant_id=current_user.tenant_id, encounter_id=encounter_id)


@encounter_router.post("/{encounter_id}/cancel", response_model=EncounterSummary)
async def cancel_encounter(
    encounter_id: uuid.UUID,
    payload: EncounterCancelRequest,
    current_user: CurrentUser = Depends(require_permission("checkin.manage")),
    service: CheckInService = Depends(get_checkin_service),
) -> EncounterSummary:
    return await service.cancel_encounter(
        tenant_id=current_user.tenant_id,
        encounter_id=encounter_id,
        payload=payload,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )


# ---- Queue / tokens ---------------------------------------------------------


@queue_router.get("", response_model=QueueListResponse)
async def search_queue(
    branch_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    status_filter: QueueTokenStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("queue.view")),
    service: CheckInService = Depends(get_checkin_service),
) -> QueueListResponse:
    return await service.search_queue(
        tenant_id=current_user.tenant_id, branch_id=branch_id, doctor_id=doctor_id, status_filter=status_filter, limit=limit, offset=offset
    )


@queue_router.post("/call-next", response_model=QueueTokenSummary)
async def call_next(
    branch_id: uuid.UUID = Query(...),
    doctor_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(require_permission("queue.manage")),
    service: CheckInService = Depends(get_checkin_service),
) -> QueueTokenSummary:
    return await service.call_next(
        tenant_id=current_user.tenant_id, branch_id=branch_id, doctor_id=doctor_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@queue_router.patch("/{token_id}", response_model=QueueTokenSummary)
async def update_token_status(
    token_id: uuid.UUID,
    payload: QueueStatusUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("queue.manage")),
    service: CheckInService = Depends(get_checkin_service),
) -> QueueTokenSummary:
    return await service.update_token_status(
        tenant_id=current_user.tenant_id,
        token_id=token_id,
        new_status=payload.status,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )
