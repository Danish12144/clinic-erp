import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.checkin.models import Encounter
from app.modules.consultation.models import Consultation, Prescription, PrescriptionItem


class ConsultationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID, doctor_id: uuid.UUID, chief_complaint: str | None
    ) -> Consultation:
        consultation = Consultation(
            tenant_id=tenant_id, encounter_id=encounter_id, doctor_id=doctor_id, chief_complaint=chief_complaint,
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(consultation)
        await self._session.flush()
        return consultation

    async def get_by_id(self, consultation_id: uuid.UUID) -> Consultation | None:
        result = await self._session.execute(select(Consultation).where(Consultation.id == consultation_id))
        return result.scalar_one_or_none()

    async def get_by_encounter_id(self, encounter_id: uuid.UUID) -> Consultation | None:
        result = await self._session.execute(select(Consultation).where(Consultation.encounter_id == encounter_id))
        return result.scalar_one_or_none()

    async def update_fields(self, consultation_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Consultation).where(Consultation.id == consultation_id).values(**fields))

    async def complete(self, consultation_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(Consultation).where(Consultation.id == consultation_id).values(ended_at=now, updated_at=now)
        )

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        encounter_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Consultation], int]:
        filters = [Consultation.tenant_id == tenant_id]
        if encounter_id:
            filters.append(Consultation.encounter_id == encounter_id)
        if doctor_id:
            filters.append(Consultation.doctor_id == doctor_id)

        query = select(Consultation)
        count_query = select(func.count()).select_from(Consultation)
        if patient_id:
            query = query.join(Encounter, Encounter.id == Consultation.encounter_id).where(Encounter.patient_id == patient_id)
            count_query = count_query.join(Encounter, Encounter.id == Consultation.encounter_id).where(Encounter.patient_id == patient_id)

        count_result = await self._session.execute(count_query.where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            query.where(*filters).order_by(Consultation.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total


class PrescriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_items(
        self,
        *,
        tenant_id: uuid.UUID,
        encounter_id: uuid.UUID,
        doctor_id: uuid.UUID,
        items: list[dict],
        supersedes_prescription_id: uuid.UUID | None = None,
    ) -> Prescription:
        prescription = Prescription(
            tenant_id=tenant_id, encounter_id=encounter_id, doctor_id=doctor_id, supersedes_prescription_id=supersedes_prescription_id
        )
        self._session.add(prescription)
        await self._session.flush()

        for item in items:
            self._session.add(PrescriptionItem(tenant_id=tenant_id, prescription_id=prescription.id, **item))
        await self._session.flush()
        await self._session.refresh(prescription, attribute_names=["id"])
        return prescription

    async def get_by_id(self, prescription_id: uuid.UUID) -> Prescription | None:
        result = await self._session.execute(
            select(Prescription).where(Prescription.id == prescription_id).options(selectinload(Prescription.items))
        )
        return result.unique().scalar_one_or_none()

    async def get_superseded_by(self, prescription_id: uuid.UUID) -> Prescription | None:
        result = await self._session.execute(select(Prescription).where(Prescription.supersedes_prescription_id == prescription_id))
        return result.scalar_one_or_none()

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        encounter_id: uuid.UUID | None,
        patient_id: uuid.UUID | None,
        doctor_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Prescription], int]:
        filters = [Prescription.tenant_id == tenant_id]
        if encounter_id:
            filters.append(Prescription.encounter_id == encounter_id)
        if doctor_id:
            filters.append(Prescription.doctor_id == doctor_id)

        base_query = select(Prescription.id)
        count_query = select(func.count()).select_from(Prescription)
        if patient_id:
            base_query = base_query.join(Encounter, Encounter.id == Prescription.encounter_id).where(Encounter.patient_id == patient_id)
            count_query = count_query.join(Encounter, Encounter.id == Prescription.encounter_id).where(Encounter.patient_id == patient_id)

        count_result = await self._session.execute(count_query.where(*filters))
        total = count_result.scalar_one()

        id_page = await self._session.execute(
            base_query.where(*filters).order_by(Prescription.issued_at.desc()).limit(limit).offset(offset)
        )
        ids = [row[0] for row in id_page.all()]
        if not ids:
            return [], total

        page_result = await self._session.execute(
            select(Prescription).where(Prescription.id.in_(ids)).options(selectinload(Prescription.items)).order_by(Prescription.issued_at.desc())
        )
        return list(page_result.unique().scalars().all()), total
