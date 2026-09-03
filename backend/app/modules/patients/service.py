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
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.patients.repository import PatientRepository
from app.modules.patients.schemas import (
    PatientCreateRequest,
    PatientCreateResponse,
    PatientListResponse,
    PatientSummary,
    PatientUpdateRequest,
)

_MAX_MRN_GENERATION_ATTEMPTS = 5


class PatientService:
    async def create_patient(self, *, tenant_id: uuid.UUID, payload: PatientCreateRequest) -> PatientCreateResponse:
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
                return PatientCreateResponse(
                    patient=PatientSummary.model_validate(patient), possible_duplicates=duplicate_summaries
                )

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
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, payload: PatientUpdateRequest
    ) -> PatientSummary:
        changes = payload.model_dump(exclude_unset=True)
        async with tenant_session(tenant_id) as session:
            repo = PatientRepository(session)
            patient = await repo.get_by_id(patient_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            await repo.update(patient_id, **changes)
            updated = await repo.get_by_id(patient_id)
            return PatientSummary.model_validate(updated)

    async def delete_patient(self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> None:
        async with tenant_session(tenant_id) as session:
            repo = PatientRepository(session)
            patient = await repo.get_by_id(patient_id)
            if patient is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
            await repo.soft_delete(patient_id)
