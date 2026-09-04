"""API surface for the Patient EMR Timeline & Medical Documents module —
PRD-ARCHITECTURE.md §8: nested under `/api/v1/patients/{patient_id}/...`.

`patients.view_emr` (Owner tenant-wide, Doctor scoped to patients they've
treated, Patient scoped to their own linked record — see service.py's
`_check_emr_access`) gates every read route here: the timeline and the
document list/detail. `patients.manage_documents` (Owner/Doctor,
unscoped) gates uploading a document — see migration 0016's docstring for
why upload isn't row-scoped the way reads are.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.emr.schemas import (
    MedicalDocumentCreateRequest,
    MedicalDocumentListResponse,
    MedicalDocumentSummary,
    PatientEmrTimeline,
)
from app.modules.emr.service import EmrService, MedicalDocumentService

emr_router = APIRouter(prefix="/api/v1/patients", tags=["emr"])
document_router = APIRouter(prefix="/api/v1/patients", tags=["medical-documents"])


def get_emr_service() -> EmrService:
    return EmrService()


def get_medical_document_service() -> MedicalDocumentService:
    return MedicalDocumentService()


@emr_router.get("/{patient_id}/emr", response_model=PatientEmrTimeline)
async def get_patient_emr_timeline(
    patient_id: uuid.UUID,
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_permission("patients.view_emr")),
    service: EmrService = Depends(get_emr_service),
) -> PatientEmrTimeline:
    return await service.get_patient_emr_timeline(
        tenant_id=current_user.tenant_id, patient_id=patient_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id,
        date_from=date_from, date_to=date_to, limit=limit,
    )


@document_router.post("/{patient_id}/documents", response_model=MedicalDocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_medical_document(
    patient_id: uuid.UUID,
    payload: MedicalDocumentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("patients.manage_documents")),
    service: MedicalDocumentService = Depends(get_medical_document_service),
) -> MedicalDocumentSummary:
    return await service.upload_document(
        tenant_id=current_user.tenant_id, patient_id=patient_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@document_router.get("/{patient_id}/documents", response_model=MedicalDocumentListResponse)
async def search_medical_documents(
    patient_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("patients.view_emr")),
    service: MedicalDocumentService = Depends(get_medical_document_service),
) -> MedicalDocumentListResponse:
    return await service.search_documents(
        tenant_id=current_user.tenant_id, patient_id=patient_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id, limit=limit, offset=offset
    )


@document_router.get("/{patient_id}/documents/{document_id}", response_model=MedicalDocumentSummary)
async def get_medical_document(
    patient_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("patients.view_emr")),
    service: MedicalDocumentService = Depends(get_medical_document_service),
) -> MedicalDocumentSummary:
    return await service.get_document(
        tenant_id=current_user.tenant_id, patient_id=patient_id, document_id=document_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id
    )
