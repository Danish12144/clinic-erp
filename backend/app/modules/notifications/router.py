"""API surface for Notification Templates & Outbox Integration —
PRD-ARCHITECTURE.md §8: `/api/v1/notifications/*`.

`notifications.manage` (Owner) gates every write route (create/update a
template, preview-render) and every read route. `notifications.view`
(Receptionist/Doctor) reaches only the read routes (list templates, list
logs) — see `require_any_permission` below. No dedicated PRD §3 matrix row
covers this; both permissions are new, by direct instruction (see
migration 0024's docstring).
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_permission
from app.modules.notifications.models import CommChannel, CommStatus
from app.modules.notifications.schemas import (
    CommunicationLogListResponse,
    NotificationTemplateCreateRequest,
    NotificationTemplateListResponse,
    NotificationTemplateSummary,
    NotificationTemplateUpdateRequest,
    SendPreviewRequest,
    SendPreviewResponse,
)
from app.modules.notifications.service import CommunicationLogService, NotificationTemplateService

_READ_PERMS = ("notifications.manage", "notifications.view")

template_router = APIRouter(prefix="/api/v1/notifications/templates", tags=["notifications"])
notification_router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def get_template_service() -> NotificationTemplateService:
    return NotificationTemplateService()


def get_log_service() -> CommunicationLogService:
    return CommunicationLogService()


@template_router.post("", response_model=NotificationTemplateSummary, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: NotificationTemplateCreateRequest,
    current_user: CurrentUser = Depends(require_permission("notifications.manage")),
    service: NotificationTemplateService = Depends(get_template_service),
) -> NotificationTemplateSummary:
    return await service.create_template(tenant_id=current_user.tenant_id, payload=payload)


@template_router.get("", response_model=NotificationTemplateListResponse)
async def search_templates(
    channel: CommChannel | None = Query(None),
    template_key: str | None = Query(None),
    is_active: bool | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: NotificationTemplateService = Depends(get_template_service),
) -> NotificationTemplateListResponse:
    return await service.search_templates(
        tenant_id=current_user.tenant_id, channel=channel, template_key=template_key, is_active=is_active, limit=limit, offset=offset,
    )


@template_router.patch("/{template_id}", response_model=NotificationTemplateSummary)
async def update_template(
    template_id: uuid.UUID,
    payload: NotificationTemplateUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("notifications.manage")),
    service: NotificationTemplateService = Depends(get_template_service),
) -> NotificationTemplateSummary:
    return await service.update_template(tenant_id=current_user.tenant_id, template_id=template_id, payload=payload)


@notification_router.post("/send-preview", response_model=SendPreviewResponse)
async def send_preview(
    payload: SendPreviewRequest,
    current_user: CurrentUser = Depends(require_permission("notifications.manage")),
    service: NotificationTemplateService = Depends(get_template_service),
) -> SendPreviewResponse:
    return await service.send_preview(tenant_id=current_user.tenant_id, template_id=payload.template_id, sample_data=payload.sample_data)


@notification_router.get("/logs", response_model=CommunicationLogListResponse)
async def search_logs(
    channel: CommChannel | None = Query(None),
    status_filter: CommStatus | None = Query(None, alias="status"),
    patient_id: uuid.UUID | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: CommunicationLogService = Depends(get_log_service),
) -> CommunicationLogListResponse:
    return await service.search_logs(
        tenant_id=current_user.tenant_id, channel=channel, status_filter=status_filter, patient_id=patient_id,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
