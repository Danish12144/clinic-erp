"""Notification Templates & Outbox Integration business logic — see
app/modules/notifications/models.py's module docstring and
PRD-ARCHITECTURE.md §20, migration 0024.

`dispatch_notification` is the shared outbox entry point every business
trigger (Appointments' booking, Billing's payment receipt, Lab's result-
ready, CRM's follow-up reminder) calls from within its own already-open
`tenant_session` — the same "free function, caller supplies the session"
pattern `record_audit`/`issue_staff_invite` already established. It looks
up an active clinic-specific `NotificationTemplate` for
`(tenant_id, channel, template_key)`; if the Owner hasn't customized that
trigger yet, it falls back to a small built-in default body per key
(`_DEFAULT_TEMPLATE_BODIES`) rather than silently dispatching nothing.
`context` is auto-enriched with `clinic_name` (looked up from `clinics`)
and, when `patient_id` is given, `patient_name` — callers only need to
supply the business-specific placeholders (`appointment_time`, `amount`,
`test_name`, ...). Exactly one `CommunicationLog` row is inserted per
call, `status=QUEUED` — still the same "stubbed outbox, no real
SMS/WhatsApp/Email provider" state every dispatch in this backend has
been in since Follow-ups first introduced the table (migration 0019).
"""

import re
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import tenant_session
from app.modules.notifications.models import CommChannel, CommStatus, CommunicationLog, NotificationTemplate
from app.modules.notifications.repository import CommunicationLogRepository, NotificationTemplateRepository
from app.modules.notifications.schemas import (
    CommunicationLogListResponse,
    CommunicationLogSummary,
    NotificationTemplateCreateRequest,
    NotificationTemplateListResponse,
    NotificationTemplateSummary,
    NotificationTemplateUpdateRequest,
    SendPreviewResponse,
)
from app.modules.patients.repository import PatientRepository
from app.modules.tenancy.repository import ClinicRepository

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")

# Best-effort defaults so a clinic that hasn't customized a trigger yet
# still gets a sensible queued message, not silence. Keyed by this task's
# own example `template_key`s — an unrecognized key with no clinic
# template renders an empty body rather than raising, since `template_key`
# is deliberately an open, non-exhaustive string (see migration 0024's
# docstring), not a closed enum this module could validate against.
_DEFAULT_TEMPLATE_BODIES: dict[str, str] = {
    "APPOINTMENT_BOOKED": "Hi {{patient_name}}, your appointment at {{clinic_name}} is booked for {{appointment_time}}.",
    "APPOINTMENT_REMINDER": "Hi {{patient_name}}, reminder: your appointment at {{clinic_name}} is on {{appointment_time}}.",
    "BILL_RECEIPT": "Hi {{patient_name}}, we've received your payment of {{amount}} at {{clinic_name}}. Thank you!",
    "LAB_RESULT_READY": "Hi {{patient_name}}, your lab report ({{test_name}}) is ready at {{clinic_name}}.",
    "FOLLOW_UP_REMINDER": "Hi {{patient_name}}, this is a reminder for your follow-up at {{clinic_name}}.",
}


def render_body(body_text: str, context: dict[str, str]) -> str:
    """`{{variable}}` interpolation — never raises: a placeholder with no
    matching context entry renders as `[variable]` rather than failing,
    since this is used both for real dispatch (context should always be
    complete) and for the `send-preview` endpoint (a deliberately
    best-effort testing tool, per this task's own wording)."""
    return _PLACEHOLDER_PATTERN.sub(lambda m: context.get(m.group(1), f"[{m.group(1)}]"), body_text)


async def dispatch_notification(
    session: AsyncSession, *, tenant_id: uuid.UUID, template_key: str, channel: CommChannel,
    patient_id: uuid.UUID | None, context: dict[str, str],
) -> CommunicationLog:
    enriched_context = dict(context)
    clinic = await ClinicRepository(session).get_by_id(tenant_id)
    enriched_context.setdefault("clinic_name", clinic.name if clinic is not None else "")
    if patient_id is not None:
        patient = await PatientRepository(session).get_by_id(patient_id)
        if patient is not None:
            full_name = f"{patient.first_name} {patient.last_name}".strip() if patient.last_name else patient.first_name
            enriched_context.setdefault("patient_name", full_name)

    template = await NotificationTemplateRepository(session).get_active(tenant_id=tenant_id, channel=channel, template_key=template_key)
    body_text = template.body_text if template is not None else _DEFAULT_TEMPLATE_BODIES.get(template_key, "")
    rendered_body = render_body(body_text, enriched_context)

    return await CommunicationLogRepository(session).create(
        tenant_id=tenant_id, patient_id=patient_id, channel=channel, status=CommStatus.QUEUED,
        template_id=template.id if template is not None else None, rendered_body=rendered_body,
    )


def _to_template_summary(template: NotificationTemplate) -> NotificationTemplateSummary:
    return NotificationTemplateSummary.model_validate(template)


class NotificationTemplateService:
    """No `record_audit` calls here, by deliberate choice — a notification
    template is admin config (wording/on-off toggle for an outbound
    message), the same "lower-stakes admin config, not a PHI/access-
    control entity" category Tenancy's clinic settings/branches were left
    un-audited for, not an oversight."""


    async def create_template(self, *, tenant_id: uuid.UUID, payload: NotificationTemplateCreateRequest) -> NotificationTemplateSummary:
        async with tenant_session(tenant_id) as session:
            try:
                template = await NotificationTemplateRepository(session).create(tenant_id=tenant_id, **payload.model_dump())
            except IntegrityError as exc:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"A template for channel '{payload.channel.value}' and key '{payload.template_key}' already exists",
                ) from exc
            return _to_template_summary(template)

    async def update_template(self, *, tenant_id: uuid.UUID, template_id: uuid.UUID, payload: NotificationTemplateUpdateRequest) -> NotificationTemplateSummary:
        async with tenant_session(tenant_id) as session:
            repo = NotificationTemplateRepository(session)
            template = await repo.get_by_id(template_id)
            if template is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")

            changes = payload.model_dump(exclude_unset=True)
            await repo.update_fields(template_id, **changes)
            updated = await repo.get_by_id(template_id)
            assert updated is not None
            return _to_template_summary(updated)

    async def search_templates(
        self, *, tenant_id: uuid.UUID, channel: CommChannel | None, template_key: str | None, is_active: bool | None,
        limit: int, offset: int,
    ) -> NotificationTemplateListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await NotificationTemplateRepository(session).search(
                tenant_id=tenant_id, channel=channel, template_key=template_key, is_active=is_active, limit=limit, offset=offset,
            )
            return NotificationTemplateListResponse(items=[_to_template_summary(t) for t in rows], total=total, limit=limit, offset=offset)

    async def send_preview(self, *, tenant_id: uuid.UUID, template_id: uuid.UUID, sample_data: dict[str, str]) -> SendPreviewResponse:
        async with tenant_session(tenant_id) as session:
            template = await NotificationTemplateRepository(session).get_by_id(template_id)
            if template is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
            rendered = render_body(template.body_text, sample_data)
            return SendPreviewResponse(template_id=template.id, rendered_body=rendered)


class CommunicationLogService:
    async def search_logs(
        self, *, tenant_id: uuid.UUID, channel: CommChannel | None, status_filter: CommStatus | None,
        patient_id: uuid.UUID | None, date_from: datetime | None, date_to: datetime | None, limit: int, offset: int,
    ) -> CommunicationLogListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await CommunicationLogRepository(session).search(
                tenant_id=tenant_id, channel=channel, status=status_filter, patient_id=patient_id,
                date_from=date_from, date_to=date_to, limit=limit, offset=offset,
            )
            return CommunicationLogListResponse(items=[CommunicationLogSummary.model_validate(l) for l in rows], total=total, limit=limit, offset=offset)
