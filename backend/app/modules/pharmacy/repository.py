import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.consultation.models import PrescriptionItem
from app.modules.pharmacy.models import InventoryTransactionType, Medicine, MedicineBatch, PharmacyInventoryTransaction


class MedicineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> Medicine:
        medicine = Medicine(tenant_id=tenant_id, **fields)
        self._session.add(medicine)
        await self._session.flush()
        return medicine

    async def get_by_id(self, medicine_id: uuid.UUID) -> Medicine | None:
        result = await self._session.execute(select(Medicine).where(Medicine.id == medicine_id))
        return result.scalar_one_or_none()

    async def update_fields(self, medicine_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Medicine).where(Medicine.id == medicine_id).values(**fields))

    async def total_stock(self, medicine_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.sum(MedicineBatch.quantity_on_hand), 0)).where(MedicineBatch.medicine_id == medicine_id)
        )
        return int(result.scalar_one())

    async def search(
        self, *, tenant_id: uuid.UUID, query_text: str | None, category: str | None, is_active: bool | None,
        low_stock_only: bool, limit: int, offset: int,
    ) -> tuple[list[tuple[Medicine, int]], int]:
        """Returns (medicine, total_stock) pairs — `total_stock` is a
        SQL-side aggregate (`SUM` across the medicine's batches), not a
        column, computed here rather than N+1 queries per row."""
        stock_subq = (
            select(MedicineBatch.medicine_id, func.coalesce(func.sum(MedicineBatch.quantity_on_hand), 0).label("total_stock"))
            .group_by(MedicineBatch.medicine_id)
            .subquery()
        )
        stock_expr = func.coalesce(stock_subq.c.total_stock, 0)

        filters = [Medicine.tenant_id == tenant_id]
        if category:
            filters.append(Medicine.category == category)
        if is_active is not None:
            filters.append(Medicine.is_active == is_active)
        if query_text:
            needle = f"%{query_text.lower()}%"
            filters.append(or_(func.lower(Medicine.name).like(needle), func.lower(func.coalesce(Medicine.generic_name, "")).like(needle)))
        if low_stock_only:
            filters.append(stock_expr < Medicine.reorder_threshold)

        base = select(Medicine, stock_expr).select_from(Medicine).outerjoin(stock_subq, stock_subq.c.medicine_id == Medicine.id).where(*filters)

        count_result = await self._session.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()

        page_result = await self._session.execute(base.order_by(Medicine.name.asc()).limit(limit).offset(offset))
        return [(row[0], int(row[1])) for row in page_result.all()], total


class MedicineBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID, batch_number: str, expiry_date: date, quantity_on_hand: int, cost_price: Decimal | None) -> MedicineBatch:
        batch = MedicineBatch(
            tenant_id=tenant_id, medicine_id=medicine_id, batch_number=batch_number, expiry_date=expiry_date,
            quantity_on_hand=quantity_on_hand, cost_price=cost_price,
        )
        self._session.add(batch)
        await self._session.flush()
        return batch

    async def get_by_id(self, batch_id: uuid.UUID) -> MedicineBatch | None:
        result = await self._session.execute(select(MedicineBatch).where(MedicineBatch.id == batch_id))
        return result.scalar_one_or_none()

    async def search(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID | None, limit: int, offset: int) -> tuple[list[MedicineBatch], int]:
        filters = [MedicineBatch.tenant_id == tenant_id]
        if medicine_id:
            filters.append(MedicineBatch.medicine_id == medicine_id)

        count_result = await self._session.execute(select(func.count()).select_from(MedicineBatch).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(MedicineBatch).where(*filters).order_by(MedicineBatch.expiry_date.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

    async def fefo_available_batches(self, *, medicine_id: uuid.UUID) -> list[MedicineBatch]:
        """First-Expiry-First-Out candidates (PRD §18) — every batch with
        stock left, soonest-expiring first. Not itself a lock; the actual
        concurrency safety is `decrement_stock`'s atomic conditional
        UPDATE below."""
        result = await self._session.execute(
            select(MedicineBatch)
            .where(MedicineBatch.medicine_id == medicine_id, MedicineBatch.quantity_on_hand > 0)
            .order_by(MedicineBatch.expiry_date.asc())
        )
        return list(result.scalars().all())

    async def decrement_stock(self, batch_id: uuid.UUID, quantity: int) -> bool:
        """Atomic compare-and-decrement: only succeeds if the batch still
        has >= `quantity` on hand *at the moment this UPDATE runs*, not at
        whatever earlier point the caller read it — safe under concurrent
        dispenses against the same batch without an explicit lock. Returns
        False (no row matched/updated) if there wasn't enough stock left,
        which the caller must treat as a hard failure, not skip silently."""
        result = await self._session.execute(
            update(MedicineBatch)
            .where(MedicineBatch.id == batch_id, MedicineBatch.quantity_on_hand >= quantity)
            .values(quantity_on_hand=MedicineBatch.quantity_on_hand - quantity, updated_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0

    async def increment_stock(self, batch_id: uuid.UUID, quantity: int) -> None:
        await self._session.execute(
            update(MedicineBatch)
            .where(MedicineBatch.id == batch_id)
            .values(quantity_on_hand=MedicineBatch.quantity_on_hand + quantity, updated_at=datetime.now(timezone.utc))
        )


class PrescriptionItemLookupRepository:
    """Reads/updates `prescription_items` (owned by the Consultation
    module) from the Pharmacy side — `dispensed_quantity` was reserved for
    exactly this since migration 0013's own docstring. Deliberately not
    added to Consultation's own `PrescriptionRepository`, since dispensing
    is this module's concern, not Consultation's."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: uuid.UUID) -> PrescriptionItem | None:
        result = await self._session.execute(select(PrescriptionItem).where(PrescriptionItem.id == item_id))
        return result.scalar_one_or_none()

    async def increment_dispensed_quantity(self, item_id: uuid.UUID, quantity: int) -> None:
        await self._session.execute(
            update(PrescriptionItem)
            .where(PrescriptionItem.id == item_id)
            .values(dispensed_quantity=PrescriptionItem.dispensed_quantity + quantity, updated_at=datetime.now(timezone.utc))
        )


class InventoryTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, batch_id: uuid.UUID, type: InventoryTransactionType, quantity_delta: int,
        reference_type: str | None, reference_id: uuid.UUID | None, performed_by: uuid.UUID, notes: str | None = None,
    ) -> PharmacyInventoryTransaction:
        txn = PharmacyInventoryTransaction(
            tenant_id=tenant_id, batch_id=batch_id, type=type, quantity_delta=quantity_delta,
            reference_type=reference_type, reference_id=reference_id, performed_by=performed_by, notes=notes,
        )
        self._session.add(txn)
        await self._session.flush()
        return txn
