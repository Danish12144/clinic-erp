import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkin.models import Encounter
from app.modules.consultation.models import Consultation
from app.modules.emr.models import MedicalDocument


class MedicalDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, encounter_id: uuid.UUID | None, document_type,
        title: str, storage_key: str, mime_type: str | None, file_size_bytes: int | None, notes: str | None, uploaded_by: uuid.UUID,
    ) -> MedicalDocument:
        document = MedicalDocument(
            tenant_id=tenant_id, patient_id=patient_id, encounter_id=encounter_id, document_type=document_type,
            title=title, storage_key=storage_key, mime_type=mime_type, file_size_bytes=file_size_bytes,
            notes=notes, uploaded_by=uploaded_by,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get_by_id(self, document_id: uuid.UUID) -> MedicalDocument | None:
        result = await self._session.execute(select(MedicalDocument).where(MedicalDocument.id == document_id))
        return result.scalar_one_or_none()

    async def search(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, encounter_id: uuid.UUID | None, limit: int, offset: int
    ) -> tuple[list[MedicalDocument], int]:
        filters = [MedicalDocument.tenant_id == tenant_id]
        if patient_id:
            filters.append(MedicalDocument.patient_id == patient_id)
        if encounter_id:
            filters.append(MedicalDocument.encounter_id == encounter_id)

        count_result = await self._session.execute(select(func.count()).select_from(MedicalDocument).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(MedicalDocument).where(*filters).order_by(MedicalDocument.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total


class EmrRepository:
    """Read-only aggregation helpers for the EMR timeline. Prescriptions
    and vitals reuse `PrescriptionRepository.search`/`VitalsRepository.
    search` directly (both already support a `patient_id` filter) — only
    the Encounter+Consultation "visit" join and the doctor-ownership check
    are specific enough to this module to live here."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def doctor_has_treated_patient(self, *, patient_id: uuid.UUID, doctor_user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(Consultation)
            .join(Encounter, Encounter.id == Consultation.encounter_id)
            .where(Encounter.patient_id == patient_id, Consultation.doctor_id == doctor_user_id)
        )
        return result.scalar_one() > 0

    async def visits(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, date_from: datetime | None, date_to: datetime | None, limit: int
    ) -> list[tuple[Encounter, Consultation]]:
        filters = [Encounter.tenant_id == tenant_id, Encounter.patient_id == patient_id]
        if date_from:
            filters.append(Encounter.checked_in_at >= date_from)
        if date_to:
            filters.append(Encounter.checked_in_at <= date_to)

        result = await self._session.execute(
            select(Encounter, Consultation)
            .join(Consultation, Consultation.encounter_id == Encounter.id)
            .where(*filters)
            .order_by(Encounter.checked_in_at.desc())
            .limit(limit)
        )
        return [(row.Encounter, row.Consultation) for row in result.all()]
