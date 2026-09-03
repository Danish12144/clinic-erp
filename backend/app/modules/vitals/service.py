"""Vitals business logic — see app/modules/vitals/models.py's module
docstring and PRD-ARCHITECTURE.md §5.1/§5.3.

Only `record_vitals` and the two read paths exist here — there is no
update/delete service method, matching the repository and the DB-level
append-only enforcement (migration 0012).
"""

import uuid
from datetime import datetime

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.checkin.models import EncounterStatus
from app.modules.checkin.repository import EncounterRepository
from app.modules.vitals.repository import VitalsRepository
from app.modules.vitals.schemas import VitalsCreateRequest, VitalsListResponse, VitalsSummary

_CLOSED_ENCOUNTER_STATUSES = (EncounterStatus.CANCELLED, EncounterStatus.COMPLETED)


class VitalsService:
    async def record_vitals(
        self, *, tenant_id: uuid.UUID, payload: VitalsCreateRequest, actor_user_id: uuid.UUID, actor_role: str
    ) -> VitalsSummary:
        async with tenant_session(tenant_id) as session:
            encounter = await EncounterRepository(session).get_by_id(payload.encounter_id)
            if encounter is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Encounter '{payload.encounter_id}' does not exist")
            if encounter.status in _CLOSED_ENCOUNTER_STATUSES:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot record vitals against an encounter with status {encounter.status.value}")

            reading = await VitalsRepository(session).create(
                tenant_id=tenant_id,
                encounter_id=encounter.id,
                patient_id=encounter.patient_id,
                recorded_by=actor_user_id,
                recorded_by_role=actor_role,
                systolic_bp=payload.systolic_bp,
                diastolic_bp=payload.diastolic_bp,
                heart_rate=payload.heart_rate,
                temperature_celsius=payload.temperature_celsius,
                spo2=payload.spo2,
                weight_kg=payload.weight_kg,
                height_cm=payload.height_cm,
                notes=payload.notes,
            )
            summary = VitalsSummary.model_validate(reading)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="vitals.record",
                entity_type="vitals",
                entity_id=reading.id,
                before=None,
                after=summary.model_dump(mode="json"),
            )
            return summary

    async def search_vitals(
        self,
        *,
        tenant_id: uuid.UUID,
        encounter_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        recorded_by: uuid.UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
        limit: int,
        offset: int,
    ) -> VitalsListResponse:
        async with tenant_session(tenant_id) as session:
            readings, total = await VitalsRepository(session).search(
                tenant_id=tenant_id,
                encounter_id=encounter_id,
                patient_id=patient_id,
                recorded_by=recorded_by,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                offset=offset,
            )
            return VitalsListResponse(items=[VitalsSummary.model_validate(v) for v in readings], total=total, limit=limit, offset=offset)

    async def get_vitals(self, *, tenant_id: uuid.UUID, vitals_id: uuid.UUID) -> VitalsSummary:
        async with tenant_session(tenant_id) as session:
            reading = await VitalsRepository(session).get_by_id(vitals_id)
            if reading is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Vitals reading not found")
            return VitalsSummary.model_validate(reading)
