"""API surface for Clinic Letterhead Configuration —
`/api/v1/letterhead/*`.

Reads (`GET .../config`, `GET .../resolve`) are open to any authenticated
staff member, not gated behind `clinic.manage_settings` — same reasoning
CLAUDE.md documents for Branches: whoever is about to print/export a
document (Doctor issuing a prescription, Receptionist printing something
at the desk) needs to resolve the letterhead layout, not just the Owner who
configured it. Writing the config (`PUT .../config`) stays Owner-only via
`clinic.manage_settings`, same as every other clinic-settings write.
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, get_current_user, require_permission
from app.modules.letterhead.schemas import LetterheadConfig, LetterheadPrintMode, LetterheadResolved
from app.modules.letterhead.service import LetterheadService

router = APIRouter(prefix="/api/v1/letterhead", tags=["letterhead"])


def get_letterhead_service() -> LetterheadService:
    return LetterheadService()


@router.get("/config", response_model=LetterheadConfig)
async def get_letterhead_config(
    current_user: CurrentUser = Depends(get_current_user), service: LetterheadService = Depends(get_letterhead_service)
) -> LetterheadConfig:
    return await service.get_config(tenant_id=current_user.tenant_id)


@router.put("/config", response_model=LetterheadConfig)
async def update_letterhead_config(
    payload: LetterheadConfig,
    current_user: CurrentUser = Depends(require_permission("clinic.manage_settings")),
    service: LetterheadService = Depends(get_letterhead_service),
) -> LetterheadConfig:
    return await service.update_config(tenant_id=current_user.tenant_id, payload=payload)


@router.get("/resolve", response_model=LetterheadResolved)
async def resolve_letterhead(
    mode: LetterheadPrintMode = Query(...),
    branch_id: uuid.UUID | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    service: LetterheadService = Depends(get_letterhead_service),
) -> LetterheadResolved:
    return await service.resolve(tenant_id=current_user.tenant_id, mode=mode, branch_id=branch_id)
