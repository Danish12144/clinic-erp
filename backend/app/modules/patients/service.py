"""Patient Management business logic: registration (with soft duplicate
detection), search, demographic updates, and soft-delete. See
PRD-ARCHITECTURE.md §5.1 (patient search/create workflow), §5.7
(corrections & cancellations — no hard-delete).

"Merge duplicate patients" (PRD §5.1: "merge is a manual owner/admin
action, never automatic") is NOT implemented here — with no other module
yet creating records that reference a patient (appointments, encounters,
invoices...), there is nothing to reassign during a merge; it would
degenerate to "delete one of the two rows," which soft-delete already
covers. Revisit once a module exists whose records would need
reassigning between two patient ids.

`_ensure_abdm_enabled_if_needed` (migration 0027) gates *writing* a
non-null `abha_id`/`abha_address` on the `features.abdm_enabled`
TenantSetting — "small clinics keep it off with zero clutter" is enforced
here, not just left as a frontend-side hint. Reading these fields back
(`PatientSummary`) is never gated by the flag — a clinic that turns ABDM
off after having set values for some patients still sees them, it just
can't set new ones until re-enabled.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import (
    PatientCreateRequest,
    PatientCreateResponse,
    PatientListResponse,
    PatientSummary,
    PatientUpdateRequest,
)
from app.modules.tenancy.repository import TenantSettingRepository

_MAX_MRN_GENERATION_ATTEMPTS = 5
_ABDM_FEATURE_KEY = "features.abdm_enabled"


async def _ensure_abdm_enabled_if_needed(session, *, tenant_id: uuid.UUID, abha_id: str | None, abha_address: str | None) -> None:
    if abha_id is None and abha_address is None:
        return
    setting = await TenantSettingRepository(session).get_by_key(tenant_id=tenant_id, key=_ABDM_FEATURE_KEY)
    if not (setting is not None and bool(setting.value)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"ABDM is not enabled for this clinic — enable '{_ABDM_FEATURE_KEY}' in clinic settings before setting abha_id/abha_address",
        )


class PatientService:
    async def create_patient(
        self,
        *,
        tenant_id: uuid.UUID,
        payload: PatientCreateRequest,
        actor_user_id: uuid.UUID,
        actor_role: str,
    ) -> PatientCreateResponse:
        async with tenant_session(tenant_id) as session:
            duplicates = await PatientRepository(session).find_possible_duplicates(
                tenant_id=tenant_id,
                phone=payload.phone,
                first_name=payload.first_name,
                last_name=payload.last_name,
                date_of_birth=payload.date_of_birth,
            )
            duplicate_summaries = [PatientSummary.model_validate(d) for d in duplicates]

        fields = payload.model_dump(exclude={"mrn"})
        explicit_mrn = payload.mrn
        attempts = 1 if explicit_mrn else _MAX_MRN_GENERATION_ATTEMPTS

        for _ in range(attempts):
            async with tenant_session(tenant_id) as session:
                await _ensure_abdm_enabled_if_needed(session, tenant_id=tenant_id, abha_id=payload.abha_id, abha_address=payload.abha_address)
                repo = PatientRepository(session)
                mrn = explicit_mrn or await repo.next_mrn_candidate(tenant_id=tenant_id)
                try:
                    patient = await repo.create(tenant_id=tenant_id, mrn=mrn, **fields)
                except IntegrityError as exc:
                    if explicit_mrn:
                        raise HTTPException(
                            status.HTTP_409_CONFLICT, f"A patient with MRN '{explicit_mrn}' already exists"
                        ) from exc
                    continue  # auto-generated candidate collided; loop retries with a fresh count-based candidate
                summary = PatientSummary.model_validate(patient)
                await record_audit(
                    session,
                    tenant_id=tenant_id,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    action="patient.create",
                    entity_type="patient",
                    entity_id=patient.id,
                    before=None,
                    after=summary.model_dump(mode="json"),
                )
                return PatientCreateResponse(patient=summary, possible_duplicates=duplicate_summaries)

        raise HTTPException(
            status.HTTP_409_CONFLICT, "Could not generate a unique medical record number — please retry"
        )

    async def search_patients(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str | None,
        phone: str | None,
        mrn: str | None,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> PatientListResponse:
        async with tenant_session(tenant_id) as session:
            patients, total = await PatientRepository(session).search(
                tenant_id=tenant_id,
                query_text=query_text,
                phone=phone,
                mrn=mrn,
                include_deleted=include_deleted,
                limit=limit,
                offset=offset,
            )
            return PatientListResponse(
                items=[PatientSummary.model_validate(p) for p in patients], total=total, limit=limit, offset=offset
            )

    async def get_patient(self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> PatientSummary:
        async with tenant_session(tenant_id) as session:
            patient = await PatientRepository(session).get_by_id(patient_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            return PatientSummary.model_validate(patient)

    async def get_my_patient_record(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> PatientSummary:
        async with tenant_session(tenant_id) as session:
            patient = await PatientRepository(session).get_by_user_id(user_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "No patient record is linked to this account")
            return PatientSummary.model_validate(patient)

    async def update_patient(
        self,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        payload: PatientUpdateRequest,
        actor_user_id: uuid.UUID,
        actor_role: str,
    ) -> PatientSummary:
        changes = payload.model_dump(exclude_unset=True)
        async with tenant_session(tenant_id) as session:
            await _ensure_abdm_enabled_if_needed(session, tenant_id=tenant_id, abha_id=changes.get("abha_id"), abha_address=changes.get("abha_address"))
            repo = PatientRepository(session)
            patient = await repo.get_by_id(patient_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            before = PatientSummary.model_validate(patient).model_dump(mode="json")
            await repo.update(patient_id, **changes)
            updated = await repo.get_by_id(patient_id)
            after = PatientSummary.model_validate(updated)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="patient.update",
                entity_type="patient",
                entity_id=patient_id,
                before=before,
                after=after.model_dump(mode="json"),
            )
            return after

    async def delete_patient(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str
    ) -> None:
        async with tenant_session(tenant_id) as session:
            repo = PatientRepository(session)
            patient = await repo.get_by_id(patient_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            before = PatientSummary.model_validate(patient).model_dump(mode="json")
            await repo.soft_delete(patient_id)
            await record_audit(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="patient.soft_delete",
                entity_type="patient",
                entity_id=patient_id,
                before=before,
                after=None,
            )
