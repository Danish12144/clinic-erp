"""API surface for Consultation and E-Prescription —
PRD-ARCHITECTURE.md §8: `/api/v1/consultations/*`, `/api/v1/prescriptions/*`.

`consultation.manage`/`prescription.manage` gate the write routes,
`consultation.view`/`prescription.view` the read ones — see migration
0013's docstring for why Owner also writes and Nurse also reads here,
diverging from the PRD §3 matrix's own default (Owner R, Doctor F-own,
Nurse none). Doctor's row-scoping ("own" per the matrix) is enforced in
the service layer, not here.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.consultation.schemas import (
    ConsultationListResponse,
    ConsultationStartRequest,
    ConsultationSummary,
    ConsultationUpdateRequest,
    PrescriptionCreateRequest,
    PrescriptionListResponse,
    PrescriptionPrintView,
    PrescriptionSummary,
)
from app.modules.consultation.service import ConsultationService, PrescriptionService
from app.modules.letterhead.schemas import LetterheadPrintMode

consultation_router = APIRouter(prefix="/api/v1/consultations", tags=["consultation"])
prescription_router = APIRouter(prefix="/api/v1/prescriptions", tags=["prescription"])


def get_consultation_service() -> ConsultationService:
    return ConsultationService()


def get_prescription_service() -> PrescriptionService:
    return PrescriptionService()


# ---- Consultations ------------------------------------------------------------


@consultation_router.post("", response_model=ConsultationSummary, status_code=status.HTTP_201_CREATED)
async def start_consultation(
    payload: ConsultationStartRequest,
    current_user: CurrentUser = Depends(require_permission("consultation.manage")),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSummary:
    return await service.start_consultation(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@consultation_router.get("", response_model=ConsultationListResponse)
async def search_consultations(
    encounter_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("consultation.view")),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationListResponse:
    return await service.search_consultations(
        tenant_id=current_user.tenant_id, encounter_id=encounter_id, patient_id=patient_id, doctor_id=doctor_id,
        actor_role=current_user.role_code, actor_user_id=current_user.user_id, limit=limit, offset=offset,
    )


@consultation_router.get("/{consultation_id}", response_model=ConsultationSummary)
async def get_consultation(
    consultation_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("consultation.view")),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSummary:
    return await service.get_consultation(
        tenant_id=current_user.tenant_id, consultation_id=consultation_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id
    )


@consultation_router.patch("/{consultation_id}", response_model=ConsultationSummary)
async def update_consultation(
    consultation_id: uuid.UUID,
    payload: ConsultationUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("consultation.manage")),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSummary:
    return await service.update_consultation(
        tenant_id=current_user.tenant_id, consultation_id=consultation_id, payload=payload,
        actor_user_id=current_user.user_id, actor_role=current_user.role_code,
    )


@consultation_router.post("/{consultation_id}/complete", response_model=ConsultationSummary)
async def complete_consultation(
    consultation_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("consultation.manage")),
    service: ConsultationService = Depends(get_consultation_service),
) -> ConsultationSummary:
    return await service.complete_consultation(
        tenant_id=current_user.tenant_id, consultation_id=consultation_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


# ---- Prescriptions --------------------------------------------------------------


@prescription_router.post("", response_model=PrescriptionSummary, status_code=status.HTTP_201_CREATED)
async def issue_prescription(
    payload: PrescriptionCreateRequest,
    current_user: CurrentUser = Depends(require_permission("prescription.manage")),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionSummary:
    return await service.issue_prescription(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@prescription_router.get("", response_model=PrescriptionListResponse)
async def search_prescriptions(
    encounter_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    doctor_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("prescription.view")),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionListResponse:
    return await service.search_prescriptions(
        tenant_id=current_user.tenant_id, encounter_id=encounter_id, patient_id=patient_id, doctor_id=doctor_id,
        actor_role=current_user.role_code, actor_user_id=current_user.user_id, limit=limit, offset=offset,
    )


@prescription_router.get("/{prescription_id}", response_model=PrescriptionSummary)
async def get_prescription(
    prescription_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("prescription.view")),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionSummary:
    return await service.get_prescription(
        tenant_id=current_user.tenant_id, prescription_id=prescription_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id
    )


@prescription_router.get("/{prescription_id}/print", response_model=PrescriptionPrintView)
async def print_prescription(
    prescription_id: uuid.UUID,
    mode: LetterheadPrintMode = Query(...),
    current_user: CurrentUser = Depends(require_permission("prescription.view")),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionPrintView:
    return await service.get_print_view(
        tenant_id=current_user.tenant_id, prescription_id=prescription_id, mode=mode,
        actor_role=current_user.role_code, actor_user_id=current_user.user_id,
    )


@prescription_router.post("/{prescription_id}/supersede", response_model=PrescriptionSummary, status_code=status.HTTP_201_CREATED)
async def supersede_prescription(
    prescription_id: uuid.UUID,
    payload: PrescriptionCreateRequest,
    current_user: CurrentUser = Depends(require_permission("prescription.manage")),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionSummary:
    return await service.supersede_prescription(
        tenant_id=current_user.tenant_id, prescription_id=prescription_id, payload=payload,
        actor_user_id=current_user.user_id, actor_role=current_user.role_code,
    )
