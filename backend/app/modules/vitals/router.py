"""API surface for the Vitals module — PRD-ARCHITECTURE.md §8:
`/api/v1/vitals/*`.

Per the PRD §3 "Vitals recording" matrix row, `vitals.record` is
configurable by the Owner per-tenant (default: Doctor/Nurse on,
Receptionist off — migration 0001's seed already matches this default;
this module does not add an Owner-facing override UI, which is a Clinic
Settings concern). `vitals.view` (migration 0012) gates the read routes,
granted to Owner/Doctor/Receptionist/Nurse — see that migration's
docstring for why Patient is deliberately excluded here.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.vitals.schemas import VitalsCreateRequest, VitalsListResponse, VitalsSummary
from app.modules.vitals.service import VitalsService

router = APIRouter(prefix="/api/v1/vitals", tags=["vitals"])


def get_vitals_service() -> VitalsService:
    return VitalsService()


@router.post("", response_model=VitalsSummary, status_code=status.HTTP_201_CREATED)
async def record_vitals(
    payload: VitalsCreateRequest,
    current_user: CurrentUser = Depends(require_permission("vitals.record")),
    service: VitalsService = Depends(get_vitals_service),
) -> VitalsSummary:
    return await service.record_vitals(
        tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code
    )


@router.get("", response_model=VitalsListResponse)
async def search_vitals(
    encounter_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    recorded_by: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("vitals.view")),
    service: VitalsService = Depends(get_vitals_service),
) -> VitalsListResponse:
    return await service.search_vitals(
        tenant_id=current_user.tenant_id,
        encounter_id=encounter_id,
        patient_id=patient_id,
        recorded_by=recorded_by,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{vitals_id}", response_model=VitalsSummary)
async def get_vitals(
    vitals_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("vitals.view")),
    service: VitalsService = Depends(get_vitals_service),
) -> VitalsSummary:
    return await service.get_vitals(tenant_id=current_user.tenant_id, vitals_id=vitals_id)
