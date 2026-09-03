import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vitals.models import Vitals


class VitalsRepository:
    """Append-only: no `update`/`delete` here by design — see
    app/modules/vitals/models.py's module docstring."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        encounter_id: uuid.UUID,
        patient_id: uuid.UUID,
        recorded_by: uuid.UUID,
        recorded_by_role: str,
        systolic_bp: int | None,
        diastolic_bp: int | None,
        heart_rate: int | None,
        temperature_celsius: float | None,
        spo2: int | None,
        weight_kg: float | None,
        height_cm: float | None,
        notes: str | None,
    ) -> Vitals:
        reading = Vitals(
            tenant_id=tenant_id,
            encounter_id=encounter_id,
            patient_id=patient_id,
            recorded_by=recorded_by,
            recorded_by_role=recorded_by_role,
            systolic_bp=systolic_bp,
            diastolic_bp=diastolic_bp,
            heart_rate=heart_rate,
            spo2=spo2,
            temperature_celsius=temperature_celsius,
            weight_kg=weight_kg,
            height_cm=height_cm,
            notes=notes,
        )
        self._session.add(reading)
        await self._session.flush()
        # bmi is DB-generated (Computed(..., persisted=True)) — SQLAlchemy
        # doesn't know its value after INSERT until it's read back.
        await self._session.refresh(reading)
        return reading

    async def get_by_id(self, vitals_id: uuid.UUID) -> Vitals | None:
        result = await self._session.execute(select(Vitals).where(Vitals.id == vitals_id))
        return result.scalar_one_or_none()

    async def search(
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
    ) -> tuple[list[Vitals], int]:
        filters = [Vitals.tenant_id == tenant_id]
        if encounter_id:
            filters.append(Vitals.encounter_id == encounter_id)
        if patient_id:
            filters.append(Vitals.patient_id == patient_id)
        if recorded_by:
            filters.append(Vitals.recorded_by == recorded_by)
        if date_from:
            filters.append(Vitals.recorded_at >= date_from)
        if date_to:
            filters.append(Vitals.recorded_at <= date_to)

        count_result = await self._session.execute(select(func.count()).select_from(Vitals).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(Vitals).where(*filters).order_by(Vitals.recorded_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total
