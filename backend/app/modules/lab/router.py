"""API surface for Pathology / Diagnostic Lab Management —
PRD-ARCHITECTURE.md §8: `/api/v1/lab/*`.

Every route here carries two dependencies: a permission check
(`require_permission`/`require_any_permission`) and the tenant feature
gate (`require_feature_flag("features.lab_enabled")`, task 4) — a clinic
that hasn't opted in gets 403 regardless of the caller's role/permissions.
`lab.manage_catalog` (Owner only, matches the PRD §3 matrix — task 5's own
framing keeps catalog definition Owner-only, unlike ordering/results)
gates catalog writes; `lab.order` (Owner/Doctor/Lab Staff) gates creating
and cancelling an order; `lab.enter_results` (Owner/Lab Staff) gates the
rest of the order lifecycle (collecting a sample, recording results,
completing/finalizing); `lab.view_results` (Owner/Doctor/Lab Staff/Patient
— Patient further scoped to their own `COMPLETED` orders at the service
layer) gates every read.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_feature_flag, require_permission
from app.modules.lab.models import LabOrderStatus
from app.modules.lab.schemas import (
    LabOrderCancelRequest,
    LabOrderCreateRequest,
    LabOrderListResponse,
    LabOrderSummary,
    LabResultCreateRequest,
    LabTestCreateRequest,
    LabTestListResponse,
    LabTestSummary,
    LabTestUpdateRequest,
)
from app.modules.lab.service import LabOrderService, LabTestService

_FEATURE_KEY = "features.lab_enabled"
_CATALOG_READ_PERMS = ("lab.manage_catalog", "lab.order", "lab.enter_results", "lab.view_results")

test_router = APIRouter(prefix="/api/v1/lab/tests", tags=["lab"])
order_router = APIRouter(prefix="/api/v1/lab", tags=["lab"])


def get_lab_test_service() -> LabTestService:
    return LabTestService()


def get_lab_order_service() -> LabOrderService:
    return LabOrderService()


# ---- Catalog ----------------------------------------------------------------------


@test_router.post("", response_model=LabTestSummary, status_code=status.HTTP_201_CREATED)
async def create_lab_test(
    payload: LabTestCreateRequest,
    current_user: CurrentUser = Depends(require_permission("lab.manage_catalog")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabTestService = Depends(get_lab_test_service),
) -> LabTestSummary:
    return await service.create_test(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@test_router.get("", response_model=LabTestListResponse)
async def search_lab_tests(
    q: str | None = Query(None),
    is_active: bool | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_CATALOG_READ_PERMS)),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabTestService = Depends(get_lab_test_service),
) -> LabTestListResponse:
    return await service.search_tests(tenant_id=current_user.tenant_id, query_text=q, is_active=is_active, limit=limit, offset=offset)


@test_router.get("/{test_id}", response_model=LabTestSummary)
async def get_lab_test(
    test_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_CATALOG_READ_PERMS)),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabTestService = Depends(get_lab_test_service),
) -> LabTestSummary:
    return await service.get_test(tenant_id=current_user.tenant_id, test_id=test_id)


@test_router.patch("/{test_id}", response_model=LabTestSummary)
async def update_lab_test(
    test_id: uuid.UUID,
    payload: LabTestUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("lab.manage_catalog")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabTestService = Depends(get_lab_test_service),
) -> LabTestSummary:
    return await service.update_test(tenant_id=current_user.tenant_id, test_id=test_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


# ---- Orders ---------------------------------------------------------------------


@order_router.post("/orders", response_model=LabOrderSummary, status_code=status.HTTP_201_CREATED)
async def create_lab_order(
    payload: LabOrderCreateRequest,
    current_user: CurrentUser = Depends(require_permission("lab.order")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.create_order(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@order_router.get("/orders", response_model=LabOrderListResponse)
async def search_lab_orders(
    patient_id: uuid.UUID | None = Query(None),
    encounter_id: uuid.UUID | None = Query(None),
    status_filter: LabOrderStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("lab.view_results")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderListResponse:
    return await service.search_orders(
        tenant_id=current_user.tenant_id, patient_id=patient_id, encounter_id=encounter_id, status_filter=status_filter,
        actor_role=current_user.role_code, actor_user_id=current_user.user_id, limit=limit, offset=offset,
    )


@order_router.get("/orders/{order_id}", response_model=LabOrderSummary)
async def get_lab_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("lab.view_results")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.get_order(tenant_id=current_user.tenant_id, order_id=order_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id)


@order_router.post("/orders/{order_id}/collect-sample", response_model=LabOrderSummary)
async def collect_sample(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("lab.enter_results")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.collect_sample(tenant_id=current_user.tenant_id, order_id=order_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@order_router.post("/orders/{order_id}/results", response_model=LabOrderSummary, status_code=status.HTTP_201_CREATED)
async def add_lab_results(
    order_id: uuid.UUID,
    payload: LabResultCreateRequest,
    current_user: CurrentUser = Depends(require_permission("lab.enter_results")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.add_results(tenant_id=current_user.tenant_id, order_id=order_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@order_router.post("/orders/{order_id}/complete", response_model=LabOrderSummary)
async def complete_lab_order(
    order_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("lab.enter_results")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.complete_order(tenant_id=current_user.tenant_id, order_id=order_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@order_router.post("/orders/{order_id}/cancel", response_model=LabOrderSummary)
async def cancel_lab_order(
    order_id: uuid.UUID,
    payload: LabOrderCancelRequest,
    current_user: CurrentUser = Depends(require_permission("lab.order")),
    _feature: CurrentUser = Depends(require_feature_flag(_FEATURE_KEY)),
    service: LabOrderService = Depends(get_lab_order_service),
) -> LabOrderSummary:
    return await service.cancel_order(tenant_id=current_user.tenant_id, order_id=order_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
