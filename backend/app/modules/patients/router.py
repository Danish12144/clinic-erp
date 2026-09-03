"""API surface for the Patient Management module —
PRD-ARCHITECTURE.md §8: `/api/v1/patients/*`.

Reads are gated behind `patients.view_demographics` (Owner, Doctor,
Receptionist, Nurse, Lab Staff, Pharmacy Staff per the PRD §3 matrix — Lab
and Pharmacy staff need to identify a patient too, even though they don't
register one). Writes (create/update/delete) require `patients.register`.
`/me` is the one exception: a PATIENT-role user viewing their own linked
record needs no permission grant, the same "own-record" pattern used by
Auth's `/me` — see app/modules/patients/service.py::get_my_patient_record.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.modules.patients.schemas import (
    PatientCreateRequest,
    PatientCreateResponse,
    PatientListResponse,
    PatientSummary,
    PatientUpdateRequest,
)
from app.modules.patients.service import PatientService

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


def get_patient_service() -> PatientService:
    return PatientService()


@router.post("", response_model=PatientCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    payload: PatientCreateRequest,
    current_user: CurrentUser = Depends(require_permission("patients.register")),
    service: PatientService = Depends(get_patient_service),
) -> PatientCreateResponse:
    return await service.create_patient(tenant_id=current_user.tenant_id, payload=payload)


@router.get("", response_model=PatientListResponse)
async def search_patients(
    q: str | None = Query(None, description="Fuzzy match against patient name"),
    phone: str | None = Query(None),
    mrn: str | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("patients.view_demographics")),
    service: PatientService = Depends(get_patient_service),
) -> PatientListResponse:
    return await service.search_patients(
        tenant_id=current_user.tenant_id,
        query_text=q,
        phone=phone,
        mrn=mrn,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.get("/me", response_model=PatientSummary)
async def get_my_patient_record(
    current_user: CurrentUser = Depends(get_current_user), service: PatientService = Depends(get_patient_service)
) -> PatientSummary:
    return await service.get_my_patient_record(tenant_id=current_user.tenant_id, user_id=current_user.user_id)


@router.get("/{patient_id}", response_model=PatientSummary)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("patients.view_demographics")),
    service: PatientService = Depends(get_patient_service),
) -> PatientSummary:
    return await service.get_patient(tenant_id=current_user.tenant_id, patient_id=patient_id)


@router.patch("/{patient_id}", response_model=PatientSummary)
async def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("patients.register")),
    service: PatientService = Depends(get_patient_service),
) -> PatientSummary:
    return await service.update_patient(tenant_id=current_user.tenant_id, patient_id=patient_id, payload=payload)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("patients.register")),
    service: PatientService = Depends(get_patient_service),
) -> None:
    await service.delete_patient(tenant_id=current_user.tenant_id, patient_id=patient_id)
