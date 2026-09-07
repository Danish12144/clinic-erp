"""Lead Pipeline / CRM Funnel business logic — see
app/modules/leads/models.py's module docstring and PRD-ARCHITECTURE.md
§20, migration 0023.

`convert_lead` is the one method that touches both `leads` and `patients`
atomically in a single DB transaction — unlike composing this module on
top of `PatientService` (a cross-module *Service* call, a pattern no other
module in this codebase uses; every existing cross-module reach stays at
the Repository/model level), it talks to `PatientRepository` directly,
inside its own `tenant_session`, so a failed lead-status update can never
leave an orphan `Patient` behind or vice versa. It reuses
`PatientRepository.next_mrn_candidate`'s auto-MRN generation and the same
up-to-5-attempts collision retry `PatientService.create_patient` uses (a
fresh `tenant_session` per attempt, since a failed INSERT aborts the
transaction) — duplicated here rather than imported, the same "each module
keeps its own small helpers" precedent Reports' doctor-ownership join
established for a similar-shaped two-line duplication.
"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.auth.repository import UserRepository
from app.modules.leads.models import Lead, LeadSource, LeadStatus
from app.modules.leads.repository import LeadInteractionRepository, LeadRepository
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
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import PatientSummary

_MAX_MRN_GENERATION_ATTEMPTS = 5
_NON_CONVERTIBLE_STATUSES = {LeadStatus.CONVERTED, LeadStatus.LOST}


def _to_summary(lead: Lead) -> LeadSummary:
    return LeadSummary.model_validate(lead)


class LeadService:
    async def create_lead(self, *, tenant_id: uuid.UUID, payload: LeadCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LeadSummary:
        async with tenant_session(tenant_id) as session:
            if payload.assigned_to_user_id is not None and await UserRepository(session).get_by_id(payload.assigned_to_user_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"User '{payload.assigned_to_user_id}' does not exist")

            lead = await LeadRepository(session).create(tenant_id=tenant_id, **payload.model_dump())
            summary = _to_summary(lead)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lead.create", entity_type="lead", entity_id=lead.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_lead(self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LeadSummary:
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("status") == LeadStatus.CONVERTED:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use POST /leads/{id}/convert to mark a lead as converted")

        async with tenant_session(tenant_id) as session:
            repo = LeadRepository(session)
            lead = await repo.get_by_id(lead_id)
            if lead is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")

            if "assigned_to_user_id" in changes and changes["assigned_to_user_id"] is not None:
                if await UserRepository(session).get_by_id(changes["assigned_to_user_id"]) is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"User '{changes['assigned_to_user_id']}' does not exist")

            before = _to_summary(lead).model_dump(mode="json")
            await repo.update_fields(lead_id, **changes)
            updated = await repo.get_by_id(lead_id)
            assert updated is not None
            after = _to_summary(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lead.update", entity_type="lead", entity_id=lead_id, before=before, after=after.model_dump(mode="json"),
            )
            return after

    async def get_lead(self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> LeadSummary:
        async with tenant_session(tenant_id) as session:
            lead = await LeadRepository(session).get_by_id(lead_id)
            if lead is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
            return _to_summary(lead)

    async def search_leads(
        self, *, tenant_id: uuid.UUID, status_filter: LeadStatus | None, source: LeadSource | None,
        assigned_to_user_id: uuid.UUID | None, date_from: datetime | None, date_to: datetime | None, limit: int, offset: int,
    ) -> LeadListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await LeadRepository(session).search(
                tenant_id=tenant_id, status=status_filter, source=source, assigned_to_user_id=assigned_to_user_id,
                date_from=date_from, date_to=date_to, limit=limit, offset=offset,
            )
            return LeadListResponse(items=[_to_summary(l) for l in rows], total=total, limit=limit, offset=offset)

    # ---- Interactions ------------------------------------------------------------

    async def log_interaction(self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadInteractionCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> LeadInteractionSummary:
        async with tenant_session(tenant_id) as session:
            if await LeadRepository(session).get_by_id(lead_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")

            interaction = await LeadInteractionRepository(session).create(
                tenant_id=tenant_id, lead_id=lead_id, interaction_type=payload.interaction_type,
                outcome=payload.outcome, notes=payload.notes, performed_by=actor_user_id,
            )
            summary = LeadInteractionSummary.model_validate(interaction)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="lead_interaction.create", entity_type="lead", entity_id=lead_id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    # ---- Conversion --------------------------------------------------------------

    async def convert_lead(self, *, tenant_id: uuid.UUID, lead_id: uuid.UUID, payload: LeadConvertRequest, actor_user_id: uuid.UUID, actor_role: str) -> LeadConvertResponse:
        for _ in range(_MAX_MRN_GENERATION_ATTEMPTS):
            async with tenant_session(tenant_id) as session:
                lead_repo = LeadRepository(session)
                lead = await lead_repo.get_by_id(lead_id)
                if lead is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
                if lead.status in _NON_CONVERTIBLE_STATUSES:
                    raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot convert a lead that is already {lead.status.value}")
                if lead.phone is None and lead.email is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Lead must have a phone number or email address to convert to a patient")

                patient_repo = PatientRepository(session)
                mrn = await patient_repo.next_mrn_candidate(tenant_id=tenant_id)
                try:
                    patient = await patient_repo.create(
                        tenant_id=tenant_id, mrn=mrn, first_name=lead.first_name, last_name=lead.last_name,
                        phone=lead.phone, email=lead.email, gender=payload.gender, date_of_birth=payload.date_of_birth,
                        address=payload.address, blood_group=None, allergies=[], chronic_conditions=[], emergency_contact=None,
                    )
                except IntegrityError:
                    continue  # auto-generated MRN candidate collided; retry with a fresh count-based candidate

                await lead_repo.update_fields(lead_id, status=LeadStatus.CONVERTED, converted_patient_id=patient.id)
                updated_lead = await lead_repo.get_by_id(lead_id)
                assert updated_lead is not None
                lead_summary = _to_summary(updated_lead)
                patient_summary = PatientSummary.model_validate(patient)

                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="patient.create", entity_type="patient", entity_id=patient.id, before=None, after=patient_summary.model_dump(mode="json"),
                )
                await record_audit(
                    session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                    action="lead.convert", entity_type="lead", entity_id=lead_id, before=None, after=lead_summary.model_dump(mode="json"),
                )
                return LeadConvertResponse(lead=lead_summary, patient_id=patient.id)

        raise HTTPException(status.HTTP_409_CONFLICT, "Could not generate a unique medical record number — please retry")
