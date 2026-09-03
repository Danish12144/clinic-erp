"""API surface for the Appointments module (booking only) —
PRD-ARCHITECTURE.md §8: `/api/v1/appointments/*`.

Per the PRD §3 matrix: booking for any patient ("Appointment booking
(staff-side)": Owner/Receptionist F) uses `appointments.manage`; a patient
booking themselves ("Online booking (patient-side)": Patient F own) uses
`appointments.book_own`, via the `/me` routes. Reading is `appointments.view`
(Owner/Receptionist/Nurse tenant-wide; Doctor's "R (own)" is enforced by
the service layer overriding any doctor_id filter to the caller's own id,
not by a separate permission — see AppointmentService.search_appointments).

The static `/me` routes are declared before the `/{appointment_id}` routes
so FastAPI matches them first — `appointment_id` is a UUID path param and
would 422 on "me" if a param route were matched first.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.appointments.models import AppointmentStatus
from app.modules.appointments.schemas import (
    AppointmentCancelRequest,
    AppointmentCreateRequest,
    AppointmentListResponse,
    AppointmentRescheduleRequest,
    AppointmentSummary,
    MyAppointmentCreateRequest,
)
from app.modules.appointments.service import AppointmentService

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])


def get_appointment_service() -> AppointmentService:
    return AppointmentService()


@router.post("", response_model=AppointmentSummary, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.manage")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.create_appointment(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@router.get("", response_model=AppointmentListResponse)
async def search_appointments(
    patient_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    branch_id: uuid.UUID | None = Query(None),
    status_filter: AppointmentStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("appointments.view")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentListResponse:
    return await service.search_appointments(
        tenant_id=current_user.tenant_id,
        actor_role=current_user.role_code,
        actor_user_id=current_user.user_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        branch_id=branch_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.post("/me", response_model=AppointmentSummary, status_code=status.HTTP_201_CREATED)
async def create_my_appointment(
    payload: MyAppointmentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.book_own")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.create_my_appointment(
        tenant_id=current_user.tenant_id, user_id=current_user.user_id, payload=payload, actor_role=current_user.role_code
    )


@router.get("/me", response_model=AppointmentListResponse)
async def get_my_appointments(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("appointments.book_own")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentListResponse:
    return await service.get_my_appointments(tenant_id=current_user.tenant_id, user_id=current_user.user_id, limit=limit, offset=offset)


@router.patch("/me/{appointment_id}", response_model=AppointmentSummary)
async def reschedule_my_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentRescheduleRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.book_own")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.reschedule_my_appointment(
        tenant_id=current_user.tenant_id, user_id=current_user.user_id, appointment_id=appointment_id, payload=payload
    )


@router.post("/me/{appointment_id}/cancel", response_model=AppointmentSummary)
async def cancel_my_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.book_own")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.cancel_my_appointment(
        tenant_id=current_user.tenant_id, user_id=current_user.user_id, appointment_id=appointment_id, reason=payload.reason
    )


@router.get("/{appointment_id}", response_model=AppointmentSummary)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("appointments.view")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.get_appointment(
        tenant_id=current_user.tenant_id, appointment_id=appointment_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id
    )


@router.patch("/{appointment_id}", response_model=AppointmentSummary)
async def reschedule_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentRescheduleRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.manage")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.reschedule_appointment(
        tenant_id=current_user.tenant_id,
        appointment_id=appointment_id,
        payload=payload,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )


@router.post("/{appointment_id}/cancel", response_model=AppointmentSummary)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    payload: AppointmentCancelRequest,
    current_user: CurrentUser = Depends(require_permission("appointments.manage")),
    service: AppointmentService = Depends(get_appointment_service),
) -> AppointmentSummary:
    return await service.cancel_appointment(
        tenant_id=current_user.tenant_id,
        appointment_id=appointment_id,
        reason=payload.reason,
        actor_user_id=current_user.user_id,
        actor_role=current_user.role_code,
    )
