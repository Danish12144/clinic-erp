"""API surface for Pharmacy & Inventory Management —
PRD-ARCHITECTURE.md §8: `/api/v1/pharmacy/*`.

`pharmacy.manage_catalog` gates catalog writes and receiving stock
(Owner/Pharmacy Staff); `pharmacy.view_catalog` gates every read route
(Owner/Pharmacy Staff/Doctor — Doctor is read-only, per the PRD §3 matrix's
"R" on "Pharmacy catalog & inventory"); `pharmacy.dispense` gates the one
write action Doctor does NOT get (matrix: Doctor "–" on "Pharmacy
dispensing / POS").

OTC sales routes (migration 0021) are additionally gated by
`require_feature_flag("features.pharmacy_enabled")` and by
`require_any_permission("pharmacy.dispense", "pharmacy.sell_otc")` —
Owner/Pharmacy Staff reach them via their existing `pharmacy.dispense`
grant, Receptionist via the new Receptionist-only `pharmacy.sell_otc`
(a direct product-owner deviation from the PRD matrix's "–" for
Receptionist on the POS row — see migration 0021's docstring). Doctor and
Nurse hold neither code, so both get a clean 403 on every sales route.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_feature_flag, require_permission
from app.modules.billing.models import PaymentMethod
from app.modules.pharmacy.models import PharmacySaleStatus
from app.modules.pharmacy.schemas import (
    DispenseRequest,
    DispenseResult,
    MedicineBatchListResponse,
    MedicineBatchSummary,
    MedicineCreateRequest,
    MedicineListResponse,
    MedicineSummary,
    MedicineUpdateRequest,
    OTCSaleCreateRequest,
    ReceiveStockRequest,
    SaleListResponse,
    SaleSummary,
)
from app.modules.pharmacy.service import PharmacyService

_FEATURE_KEY = "features.pharmacy_enabled"
_SALES_PERMS = ("pharmacy.dispense", "pharmacy.sell_otc")

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


# ---- OTC / Retail sales -----------------------------------------------------------


@pharmacy_router.post("/sales", response_model=SaleSummary, status_code=status.HTTP_201_CREATED)
async def checkout_otc_sale(
    payload: OTCSaleCreateRequest,
    current_user: CurrentUser = Depends(require_any_permission(*_SALES_PERMS)),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> SaleSummary:
    return await service.checkout_otc_sale(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@pharmacy_router.get("/sales", response_model=SaleListResponse)
async def search_otc_sales(
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    payment_mode: PaymentMethod | None = Query(None),
    status_filter: PharmacySaleStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_SALES_PERMS)),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> SaleListResponse:
    return await service.search_sales(
        tenant_id=current_user.tenant_id, date_from=date_from, date_to=date_to, payment_mode=payment_mode,
        status_filter=status_filter, limit=limit, offset=offset,
    )


@pharmacy_router.get("/sales/{sale_id}", response_model=SaleSummary)
async def get_otc_sale(
    sale_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_SALES_PERMS)),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: PharmacyService = Depends(get_pharmacy_service),
) -> SaleSummary:
    return await service.get_sale(tenant_id=current_user.tenant_id, sale_id=sale_id)
