"""API surface for reading the audit log — PRD-ARCHITECTURE.md §14, §8:
`/api/v1/audit-logs`. Read-only by design; nothing ever writes here over
HTTP — see app/modules/audit/service.py::record, called directly from
other modules' service layers within their own transactions.
"""

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, require_permission
from app.modules.audit.schemas import AuditLogListResponse
from app.modules.audit.service import AuditLogService

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


def get_audit_log_service() -> AuditLogService:
    return AuditLogService()


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    entity_type: str | None = Query(None),
    entity_id: uuid.UUID | None = Query(None),
    actor_user_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("audit.view")),
    service: AuditLogService = Depends(get_audit_log_service),
) -> AuditLogListResponse:
    return await service.list_logs(
        tenant_id=current_user.tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        limit=limit,
        offset=offset,
    )
