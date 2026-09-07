"""API surface for Lead Pipeline / CRM Funnel — PRD-ARCHITECTURE.md §8:
`/api/v1/leads/*`.

`leads.manage` (Owner/Receptionist) gates every write route (create,
update, log an interaction, convert) and every read route.
`leads.view` (Doctor) reaches only the read routes — see
`require_any_permission` on `search_leads`/`get_lead`. Deliberately not
built on the existing `crm.manage` permission (Owner/Receptionist/
Doctor-for-their-own-follow-ups since migration 0019) despite the PRD §3
matrix modeling "CRM, leads, follow-ups" as one row — see migration 0023's
docstring for why reusing it here would have silently handed Doctor write
access to leads too.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_permission
from app.modules.leads.models import LeadSource, LeadStatus
from app.modules.leads.schemas import (
    LeadConvertRequest,
    LeadConvertResponse,
    LeadCreateRequest,
    LeadInteractionCreateRequest,
    LeadInteractionSummary,
    LeadListResponse,
    LeadSummary,
    LeadUpdateRequest,
)
from app.modules.leads.service import LeadService

_READ_PERMS = ("leads.manage", "leads.view")

router = APIRouter(prefix="/api/v1/leads", tags=["leads"])


def get_lead_service() -> LeadService:
    return LeadService()


@router.post("", response_model=LeadSummary, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreateRequest,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    service: LeadService = Depends(get_lead_service),
) -> LeadSummary:
    return await service.create_lead(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@router.get("", response_model=LeadListResponse)
async def search_leads(
    status_filter: LeadStatus | None = Query(None, alias="status"),
    source: LeadSource | None = Query(None),
    assigned_to_user_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: LeadService = Depends(get_lead_service),
) -> LeadListResponse:
    return await service.search_leads(
        tenant_id=current_user.tenant_id, status_filter=status_filter, source=source, assigned_to_user_id=assigned_to_user_id,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )


@router.get("/{lead_id}", response_model=LeadSummary)
async def get_lead(
    lead_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: LeadService = Depends(get_lead_service),
) -> LeadSummary:
    return await service.get_lead(tenant_id=current_user.tenant_id, lead_id=lead_id)


@router.patch("/{lead_id}", response_model=LeadSummary)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    service: LeadService = Depends(get_lead_service),
) -> LeadSummary:
    return await service.update_lead(tenant_id=current_user.tenant_id, lead_id=lead_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@router.post("/{lead_id}/interactions", response_model=LeadInteractionSummary, status_code=status.HTTP_201_CREATED)
async def log_interaction(
    lead_id: uuid.UUID,
    payload: LeadInteractionCreateRequest,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    service: LeadService = Depends(get_lead_service),
) -> LeadInteractionSummary:
    return await service.log_interaction(tenant_id=current_user.tenant_id, lead_id=lead_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@router.post("/{lead_id}/convert", response_model=LeadConvertResponse)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvertRequest,
    current_user: CurrentUser = Depends(require_permission("leads.manage")),
    service: LeadService = Depends(get_lead_service),
) -> LeadConvertResponse:
    return await service.convert_lead(tenant_id=current_user.tenant_id, lead_id=lead_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
