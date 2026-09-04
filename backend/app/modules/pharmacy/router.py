"""API surface for Pharmacy & Inventory Management —
PRD-ARCHITECTURE.md §8: `/api/v1/pharmacy/*`.

`pharmacy.manage_catalog` gates catalog writes and receiving stock
(Owner/Pharmacy Staff); `pharmacy.view_catalog` gates every read route
(Owner/Pharmacy Staff/Doctor — Doctor is read-only, per the PRD §3 matrix's
"R" on "Pharmacy catalog & inventory"); `pharmacy.dispense` gates the one
write action Doctor does NOT get (matrix: Doctor "–" on "Pharmacy
dispensing / POS").
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_permission
from app.modules.pharmacy.schemas import (
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
from app.modules.pharmacy.service import PharmacyService

medicine_router = APIRouter(prefix="/api/v1/pharmacy/medicines", tags=["pharmacy"])
pharmacy_router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


def get_pharmacy_service() -> PharmacyService:
    return PharmacyService()


# ---- Medicines ------------------------------------------------------------------


@medicine_router.post("", response_model=MedicineSummary, status_code=status.HTTP_201_CREATED)
async def create_medicine(
    payload: MedicineCreateRequest,
    current_user: CurrentUser = Depends(require_permission("pharmacy.manage_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineSummary:
    return await service.create_medicine(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@medicine_router.get("", response_model=MedicineListResponse)
async def search_medicines(
    q: str | None = Query(None, description="Fuzzy match against name/generic name"),
    category: str | None = Query(None),
    is_active: bool | None = Query(None),
    low_stock_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("pharmacy.view_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineListResponse:
    return await service.search_medicines(
        tenant_id=current_user.tenant_id, query_text=q, category=category, is_active=is_active,
        low_stock_only=low_stock_only, limit=limit, offset=offset,
    )


@medicine_router.get("/{medicine_id}", response_model=MedicineSummary)
async def get_medicine(
    medicine_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("pharmacy.view_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineSummary:
    return await service.get_medicine(tenant_id=current_user.tenant_id, medicine_id=medicine_id)


@medicine_router.patch("/{medicine_id}", response_model=MedicineSummary)
async def update_medicine(
    medicine_id: uuid.UUID,
    payload: MedicineUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("pharmacy.manage_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineSummary:
    return await service.update_medicine(tenant_id=current_user.tenant_id, medicine_id=medicine_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@medicine_router.post("/{medicine_id}/batches", response_model=MedicineBatchSummary, status_code=status.HTTP_201_CREATED)
async def receive_stock(
    medicine_id: uuid.UUID,
    payload: ReceiveStockRequest,
    current_user: CurrentUser = Depends(require_permission("pharmacy.manage_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineBatchSummary:
    return await service.receive_stock(tenant_id=current_user.tenant_id, medicine_id=medicine_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@medicine_router.get("/{medicine_id}/batches", response_model=MedicineBatchListResponse)
async def search_medicine_batches(
    medicine_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("pharmacy.view_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineBatchListResponse:
    return await service.search_batches(tenant_id=current_user.tenant_id, medicine_id=medicine_id, limit=limit, offset=offset)


# ---- Batches (cross-medicine) + dispensing ---------------------------------------


@pharmacy_router.get("/batches/{batch_id}", response_model=MedicineBatchSummary)
async def get_batch(
    batch_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("pharmacy.view_catalog")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> MedicineBatchSummary:
    return await service.get_batch(tenant_id=current_user.tenant_id, batch_id=batch_id)


@pharmacy_router.post("/dispense", response_model=DispenseResult, status_code=status.HTTP_201_CREATED)
async def dispense_prescription_item(
    payload: DispenseRequest,
    current_user: CurrentUser = Depends(require_permission("pharmacy.dispense")),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> DispenseResult:
    return await service.dispense_prescription_item(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
