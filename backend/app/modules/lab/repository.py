import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.lab.models import LabOrder, LabOrderStatus, LabResult, LabTestCatalogItem


class LabTestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> LabTestCatalogItem:
        test = LabTestCatalogItem(tenant_id=tenant_id, **fields)
        self._session.add(test)
        await self._session.flush()
        return test

    async def get_by_id(self, test_id: uuid.UUID) -> LabTestCatalogItem | None:
        result = await self._session.execute(select(LabTestCatalogItem).where(LabTestCatalogItem.id == test_id))
        return result.scalar_one_or_none()

    async def update_fields(self, test_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(LabTestCatalogItem).where(LabTestCatalogItem.id == test_id).values(**fields))

    async def search(self, *, tenant_id: uuid.UUID, query_text: str | None, is_active: bool | None, limit: int, offset: int) -> tuple[list[LabTestCatalogItem], int]:
        filters = [LabTestCatalogItem.tenant_id == tenant_id]
        if is_active is not None:
            filters.append(LabTestCatalogItem.is_active == is_active)
        if query_text:
            needle = f"%{query_text.lower()}%"
            filters.append(func.lower(LabTestCatalogItem.name).like(needle))

        count_result = await self._session.execute(select(func.count()).select_from(LabTestCatalogItem).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(LabTestCatalogItem).where(*filters).order_by(LabTestCatalogItem.name.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total


def _with_relations(query):
    # populate_existing=True: this module's service re-fetches the same
    # LabOrder more than once per request (create -> re-fetch, add results
    # -> re-fetch) — see app/modules/billing/repository.py's
    # `_with_relations` for the identity-map staleness this avoids.
    return query.options(selectinload(LabOrder.test), selectinload(LabOrder.results)).execution_options(populate_existing=True)


class LabOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, encounter_id: uuid.UUID, patient_id: uuid.UUID, doctor_id: uuid.UUID | None, test_id: uuid.UUID, ordered_by: uuid.UUID) -> LabOrder:
        order = LabOrder(tenant_id=tenant_id, encounter_id=encounter_id, patient_id=patient_id, doctor_id=doctor_id, test_id=test_id, ordered_by=ordered_by)
        self._session.add(order)
        await self._session.flush()
        return order

    async def get_by_id(self, order_id: uuid.UUID) -> LabOrder | None:
        result = await self._session.execute(_with_relations(select(LabOrder).where(LabOrder.id == order_id)))
        return result.unique().scalar_one_or_none()

    async def update_fields(self, order_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(LabOrder).where(LabOrder.id == order_id).values(**fields))

    async def search(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, encounter_id: uuid.UUID | None,
        status: LabOrderStatus | None, only_completed: bool, limit: int, offset: int,
    ) -> tuple[list[LabOrder], int]:
        """No doctor-ownership scoping here, unlike Billing/Reports — the
        PRD §3 matrix's "Lab result entry & reports" row gives Doctor a
        plain "R", not "R (own)" the way Billing's row does, so Doctor
        reads are tenant-wide, gated only by `lab.view_results` (see
        `LabOrderService`). Only `patient_id`/`encounter_id`/`status`
        filter."""
        filters = [LabOrder.tenant_id == tenant_id]
        if patient_id:
            filters.append(LabOrder.patient_id == patient_id)
        if encounter_id:
            filters.append(LabOrder.encounter_id == encounter_id)
        if status:
            filters.append(LabOrder.status == status)
        if only_completed:
            filters.append(LabOrder.status == LabOrderStatus.COMPLETED)

        count_result = await self._session.execute(select(func.count()).select_from(LabOrder).where(*filters))
        total = count_result.scalar_one()

        id_page = await self._session.execute(select(LabOrder.id).where(*filters).order_by(LabOrder.created_at.desc()).limit(limit).offset(offset))
        ids = [row[0] for row in id_page.all()]
        if not ids:
            return [], total

        page_result = await self._session.execute(_with_relations(select(LabOrder).where(LabOrder.id.in_(ids))).order_by(LabOrder.created_at.desc()))
        return list(page_result.unique().scalars().all()), total


class LabResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, lab_order_id: uuid.UUID, parameter: str, value: str, unit: str | None, reference_range: str | None, flag, entered_by: uuid.UUID) -> LabResult:
        result = LabResult(
            tenant_id=tenant_id, lab_order_id=lab_order_id, parameter=parameter, value=value, unit=unit,
            reference_range=reference_range, flag=flag, entered_by=entered_by,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def finalize_all_for_order(self, lab_order_id: uuid.UUID) -> None:
        await self._session.execute(
            update(LabResult).where(LabResult.lab_order_id == lab_order_id, LabResult.finalized_at.is_(None)).values(finalized_at=datetime.now(timezone.utc))
        )
