"""Pharmacy & Inventory Management business logic — see
app/modules/pharmacy/models.py's module docstring and
PRD-ARCHITECTURE.md §18.

`dispense_prescription_item` is the one method that touches three
tables atomically in a single DB transaction (`medicine_batches`,
`pharmacy_inventory_transactions`, and Consultation's own
`prescription_items`): FEFO-select candidate batches, atomically
decrement each one (`MedicineBatchRepository.decrement_stock`'s
compare-and-decrement — safe under concurrency without an explicit
lock), log a `DISPENSE` transaction per batch drawn from, then bump the
prescription item's `dispensed_quantity`. Any failure partway rolls back
the whole thing, since it's all one `tenant_session`.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.pharmacy.models import InventoryTransactionType, Medicine
from app.modules.pharmacy.repository import (
    InventoryTransactionRepository,
    MedicineBatchRepository,
    MedicineRepository,
    PrescriptionItemLookupRepository,
)
from app.modules.pharmacy.schemas import (
    DispenseAllocation,
    DispenseRequest,
    DispenseResult,
    MedicineBatchListResponse,
    MedicineBatchSummary,
    MedicineCreateRequest,
    MedicineListResponse,
    MedicineSummary,
    MedicineUpdateRequest,
    ReceiveStockRequest,
)


def _to_medicine_summary(medicine: Medicine, total_stock: int) -> MedicineSummary:
    return MedicineSummary(
        id=medicine.id, tenant_id=medicine.tenant_id, name=medicine.name, generic_name=medicine.generic_name,
        category=medicine.category, dosage_form=medicine.dosage_form, strength=medicine.strength,
        manufacturer=medicine.manufacturer, unit_price=medicine.unit_price, sku=medicine.sku,
        reorder_threshold=medicine.reorder_threshold, is_active=medicine.is_active, total_stock=total_stock,
        is_below_reorder_threshold=total_stock < medicine.reorder_threshold,
        created_at=medicine.created_at, updated_at=medicine.updated_at,
    )


class PharmacyService:
    # ---- Medicines -----------------------------------------------------------

    async def create_medicine(self, *, tenant_id: uuid.UUID, payload: MedicineCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> MedicineSummary:
        async with tenant_session(tenant_id) as session:
            repo = MedicineRepository(session)
            try:
                medicine = await repo.create(tenant_id=tenant_id, **payload.model_dump())
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, f"A medicine with SKU '{payload.sku}' already exists") from exc
            summary = _to_medicine_summary(medicine, total_stock=0)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="medicine.create", entity_type="medicine", entity_id=medicine.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_medicine(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID, payload: MedicineUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> MedicineSummary:
        changes = payload.model_dump(exclude_unset=True)
        async with tenant_session(tenant_id) as session:
            repo = MedicineRepository(session)
            medicine = await repo.get_by_id(medicine_id)
            if medicine is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Medicine not found")
            before = _to_medicine_summary(medicine, total_stock=await repo.total_stock(medicine_id)).model_dump(mode="json")
            try:
                await repo.update_fields(medicine_id, **changes)
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, "A medicine with that SKU already exists") from exc
            updated = await repo.get_by_id(medicine_id)
            total_stock = await repo.total_stock(medicine_id)
            after = _to_medicine_summary(updated, total_stock)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="medicine.update", entity_type="medicine", entity_id=medicine_id, before=before, after=after.model_dump(mode="json"),
            )
            return after

    async def get_medicine(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID) -> MedicineSummary:
        async with tenant_session(tenant_id) as session:
            repo = MedicineRepository(session)
            medicine = await repo.get_by_id(medicine_id)
            if medicine is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Medicine not found")
            return _to_medicine_summary(medicine, await repo.total_stock(medicine_id))

    async def search_medicines(
        self, *, tenant_id: uuid.UUID, query_text: str | None, category: str | None, is_active: bool | None,
        low_stock_only: bool, limit: int, offset: int,
    ) -> MedicineListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await MedicineRepository(session).search(
                tenant_id=tenant_id, query_text=query_text, category=category, is_active=is_active,
                low_stock_only=low_stock_only, limit=limit, offset=offset,
            )
            return MedicineListResponse(items=[_to_medicine_summary(m, stock) for m, stock in rows], total=total, limit=limit, offset=offset)

    # ---- Batches / receiving stock --------------------------------------------

    async def receive_stock(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID, payload: ReceiveStockRequest, actor_user_id: uuid.UUID, actor_role: str) -> MedicineBatchSummary:
        async with tenant_session(tenant_id) as session:
            if await MedicineRepository(session).get_by_id(medicine_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Medicine '{medicine_id}' does not exist")

            batch_repo = MedicineBatchRepository(session)
            try:
                batch = await batch_repo.create(
                    tenant_id=tenant_id, medicine_id=medicine_id, batch_number=payload.batch_number,
                    expiry_date=payload.expiry_date, quantity_on_hand=payload.quantity, cost_price=payload.cost_price,
                )
            except IntegrityError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Batch '{payload.batch_number}' already exists for this medicine") from exc

            await InventoryTransactionRepository(session).create(
                tenant_id=tenant_id, batch_id=batch.id, type=InventoryTransactionType.RECEIVE, quantity_delta=payload.quantity,
                reference_type=None, reference_id=None, performed_by=actor_user_id,
            )
            summary = MedicineBatchSummary.model_validate(batch)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="medicine_batch.receive", entity_type="medicine_batch", entity_id=batch.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def search_batches(self, *, tenant_id: uuid.UUID, medicine_id: uuid.UUID | None, limit: int, offset: int) -> MedicineBatchListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total = await MedicineBatchRepository(session).search(tenant_id=tenant_id, medicine_id=medicine_id, limit=limit, offset=offset)
            return MedicineBatchListResponse(items=[MedicineBatchSummary.model_validate(b) for b in rows], total=total, limit=limit, offset=offset)

    async def get_batch(self, *, tenant_id: uuid.UUID, batch_id: uuid.UUID) -> MedicineBatchSummary:
        async with tenant_session(tenant_id) as session:
            batch = await MedicineBatchRepository(session).get_by_id(batch_id)
            if batch is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Batch not found")
            return MedicineBatchSummary.model_validate(batch)

    # ---- Dispensing ------------------------------------------------------------

    async def dispense_prescription_item(self, *, tenant_id: uuid.UUID, payload: DispenseRequest, actor_user_id: uuid.UUID, actor_role: str) -> DispenseResult:
        async with tenant_session(tenant_id) as session:
            item_repo = PrescriptionItemLookupRepository(session)
            item = await item_repo.get_by_id(payload.prescription_item_id)
            if item is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription item not found")
            if item.medicine_id is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This prescription item has no linked catalog medicine and cannot be dispensed from inventory")

            remaining_prescribed = item.prescribed_quantity - item.dispensed_quantity
            if payload.quantity > remaining_prescribed:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot dispense {payload.quantity}; only {remaining_prescribed} remain on this prescription item")

            batch_repo = MedicineBatchRepository(session)
            candidates = await batch_repo.fefo_available_batches(medicine_id=item.medicine_id)
            remaining = payload.quantity
            planned: list[tuple[uuid.UUID, str, int]] = []
            for batch in candidates:
                if remaining <= 0:
                    break
                take = min(batch.quantity_on_hand, remaining)
                planned.append((batch.id, batch.batch_number, take))
                remaining -= take
            if remaining > 0:
                raise HTTPException(status.HTTP_409_CONFLICT, "Insufficient stock across all batches to dispense the requested quantity")

            txn_repo = InventoryTransactionRepository(session)
            allocations: list[DispenseAllocation] = []
            for batch_id, batch_number, take in planned:
                if not await batch_repo.decrement_stock(batch_id, take):
                    # Someone else drained this batch between our FEFO read
                    # and now — fail the whole dispense rather than
                    # under-fill it silently; the transaction rolls back.
                    raise HTTPException(status.HTTP_409_CONFLICT, "Stock changed concurrently — please retry the dispense")
                await txn_repo.create(
                    tenant_id=tenant_id, batch_id=batch_id, type=InventoryTransactionType.DISPENSE, quantity_delta=-take,
                    reference_type="PRESCRIPTION_ITEM", reference_id=item.id, performed_by=actor_user_id,
                )
                allocations.append(DispenseAllocation(batch_id=batch_id, batch_number=batch_number, quantity=take))

            await item_repo.increment_dispensed_quantity(item.id, payload.quantity)
            # Re-fetch rather than compute `item.dispensed_quantity +
            # payload.quantity` in Python: SQLAlchemy's ORM-aware bulk
            # UPDATE can "evaluate" the SET expression against already-
            # loaded objects matching the WHERE clause and silently patch
            # their in-memory attributes to match — `item.dispensed_quantity`
            # may already reflect the increment by this point, and adding
            # the delta again would double-count it.
            updated_item = await item_repo.get_by_id(item.id)
            assert updated_item is not None
            new_dispensed_quantity = updated_item.dispensed_quantity

            result = DispenseResult(
                prescription_item_id=item.id, medicine_id=item.medicine_id, quantity_dispensed=payload.quantity,
                prescription_item_dispensed_quantity=new_dispensed_quantity, allocations=allocations,
            )
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="pharmacy.dispense", entity_type="prescription_item", entity_id=item.id, before=None, after=result.model_dump(mode="json"),
            )
            return result
