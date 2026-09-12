"""Public (unauthenticated) clinic discovery + self-booking API surface —
Phase 2 (Master Handoff item 1): `/api/v1/public/clinics/{clinic_slug}/*`.
No `Depends(require_permission(...))` anywhere here, by design — matching
`app.modules.auth.router`'s own staff-login/OTP endpoints, the only other
routes in this codebase reachable with zero prior authentication.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.modules.public.schemas import (
    PublicBookingRequest,
    PublicBookingResponse,
    PublicBranchSummary,
    PublicClinicSummary,
    PublicDoctorSummary,
    PublicGatewayOrderInfo,
    PublicRetryPaymentRequest,
    PublicSlotsResponse,
)
from app.modules.public.service import PublicBookingService

router = APIRouter(prefix="/api/v1/public/clinics", tags=["public"])


def get_public_booking_service() -> PublicBookingService:
    return PublicBookingService()


@router.get("/{clinic_slug}", response_model=PublicClinicSummary)
async def get_clinic(clinic_slug: str, service: PublicBookingService = Depends(get_public_booking_service)) -> PublicClinicSummary:
    return await service.get_clinic(clinic_slug=clinic_slug)


@router.get("/{clinic_slug}/branches", response_model=list[PublicBranchSummary])
async def list_branches(clinic_slug: str, service: PublicBookingService = Depends(get_public_booking_service)) -> list[PublicBranchSummary]:
    return await service.list_branches(clinic_slug=clinic_slug)


@router.get("/{clinic_slug}/doctors", response_model=list[PublicDoctorSummary])
async def list_doctors(
    clinic_slug: str, branch_id: uuid.UUID | None = Query(None), service: PublicBookingService = Depends(get_public_booking_service)
) -> list[PublicDoctorSummary]:
    return await service.list_doctors(clinic_slug=clinic_slug, branch_id=branch_id)


@router.get("/{clinic_slug}/doctors/{doctor_id}/slots", response_model=PublicSlotsResponse)
async def list_slots(
    clinic_slug: str, doctor_id: uuid.UUID, on: date = Query(..., description="Date to list available slots for"),
    service: PublicBookingService = Depends(get_public_booking_service),
) -> PublicSlotsResponse:
    return await service.list_slots(clinic_slug=clinic_slug, doctor_id=doctor_id, target_date=on)


@router.post("/{clinic_slug}/book", response_model=PublicBookingResponse, status_code=201)
async def book(
    clinic_slug: str, payload: PublicBookingRequest, service: PublicBookingService = Depends(get_public_booking_service)
) -> PublicBookingResponse:
    return await service.book(clinic_slug=clinic_slug, payload=payload)


@router.post("/{clinic_slug}/appointments/{appointment_id}/retry-payment", response_model=PublicGatewayOrderInfo)
async def retry_payment(
    clinic_slug: str, appointment_id: uuid.UUID, payload: PublicRetryPaymentRequest,
    service: PublicBookingService = Depends(get_public_booking_service),
) -> PublicGatewayOrderInfo:
    return await service.retry_payment(clinic_slug=clinic_slug, appointment_id=appointment_id, phone=payload.phone)
