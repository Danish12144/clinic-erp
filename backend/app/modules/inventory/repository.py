import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import InventoryChangeType, InventoryItem, InventoryItemCategory, InventoryTransaction


class InventoryItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, **fields: object) -> InventoryItem:
        item = InventoryItem(tenant_id=tenant_id, **fields)
        self._session.add(item)
        await self._session.flush()
        return item

    async def get_by_id(self, item_id: uuid.UUID) -> InventoryItem | None:
        result = await self._session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
        return result.scalar_one_or_none()

    async def update_fields(self, item_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(InventoryItem).where(InventoryItem.id == item_id).values(**fields))

    async def apply_delta(self, item_id: uuid.UUID, delta: Decimal) -> bool:
        """Atomic conditional UPDATE — same "let Postgres re-validate
        against the live value" pattern as Pharmacy's
        `MedicineBatchRepository.decrement_stock`. Works for any sign of
        `delta`: a positive delta always satisfies the WHERE clause since
        `current_stock` is already DB-CHECK'd non-negative; a negative
        delta (USAGE, or a negative ADJUSTMENT) only succeeds if enough
        stock remains, closing the negative-stock race window without an
        explicit lock. Returns False if it would have gone negative."""
        result = await self._session.execute(
            update(InventoryItem)
            .where(InventoryItem.id == item_id, InventoryItem.current_stock + delta >= 0)
            .values(current_stock=InventoryItem.current_stock + delta, updated_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0

    async def search(
        self, *, tenant_id: uuid.UUID, category: InventoryItemCategory | None, is_active: bool | None,
        low_stock_only: bool, limit: int, offset: int,
    ) -> tuple[list[InventoryItem], int]:
        filters = [InventoryItem.tenant_id == tenant_id]
        if category:
            filters.append(InventoryItem.category == category)
        if is_active is not None:
            filters.append(InventoryItem.is_active == is_active)
        if low_stock_only:
            filters.append(InventoryItem.current_stock < InventoryItem.min_reorder_level)

        count_result = await self._session.execute(select(func.count()).select_from(InventoryItem).where(*filters))
        total = count_result.scalar_one()

        page_result = await self._session.execute(
            select(InventoryItem).where(*filters).order_by(InventoryItem.name.asc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total

    async def list_low_stock(self, *, tenant_id: uuid.UUID) -> list[InventoryItem]:
        """Every breaching item, unpaginated — "list all items breaching
        min_reorder_level," not a filtered page of them."""
        result = await self._session.execute(
            select(InventoryItem)
            .where(InventoryItem.tenant_id == tenant_id, InventoryItem.is_active.is_(True), InventoryItem.current_stock < InventoryItem.min_reorder_level)
            .order_by(InventoryItem.name.asc())
        )
        return list(result.scalars().all())


class InventoryTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, tenant_id: uuid.UUID, item_id: uuid.UUID, change_type: InventoryChangeType, quantity: Decimal,
        reference_id: uuid.UUID | None, performed_by: uuid.UUID, notes: str | None,
    ) -> InventoryTransaction:
        txn = InventoryTransaction(
            tenant_id=tenant_id, item_id=item_id, change_type=change_type, quantity=quantity,
            reference_id=reference_id, performed_by=performed_by, notes=notes,
        )
        self._session.add(txn)
        await self._session.flush()
        return txn
