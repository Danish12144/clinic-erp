"""API surface for Billing, Invoices & Payments —
PRD-ARCHITECTURE.md §8: `/api/v1/billing/invoices/*`, `/api/v1/billing/payments/*`.

Per the PRD §3 matrix (no deviation here, unlike Consultation): Owner/
Receptionist hold `billing.manage` (full, gates every write route here)
and `payments.record` (full, gates both payment routes); Doctor and
Patient hold `billing.view_own` (read, row-scoped in the service layer —
Doctor to their own consulted encounters, Patient to their own
`patient_id`). Reads use `require_any_permission` since two differently-
scoped permission codes both reach the same route — see app/api/deps.py.
Doctor/Patient have no access to `payments.*` at all (matrix: Doctor "–",
Patient "O read" — satisfied by payments being nested inside
`InvoiceSummary.payments`, not a separate grant).

The static `/me` route is declared before `/{invoice_id}` so FastAPI
matches it first, same reasoning as Appointments' `/me` routes.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_permission
from app.modules.billing.models import InvoiceStatus
from app.modules.billing.schemas import (
    AutoGenerateInvoiceRequest,
    InvoiceCreateRequest,
    InvoiceLineItemCreateRequest,
    InvoiceLineItemUpdateRequest,
    InvoiceListResponse,
    InvoiceSummary,
    InvoiceUpdateRequest,
    InvoiceVoidRequest,
    PaymentCreateRequest,
    PaymentListResponse,
    PaymentOrderResponse,
    PaymentSummary,
)
from app.modules.billing.service import BillingService, PaymentService

invoice_router = APIRouter(prefix="/api/v1/billing/invoices", tags=["billing:invoices"])
payment_router = APIRouter(prefix="/api/v1/billing/payments", tags=["billing:payments"])

_READ_PERMS = ("billing.manage", "billing.view_own")


def get_billing_service() -> BillingService:
    return BillingService()


def get_payment_service() -> PaymentService:
    return PaymentService()


# ---- Invoices -----------------------------------------------------------------


@invoice_router.post("", response_model=InvoiceSummary, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: InvoiceCreateRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.create_invoice(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.post("/auto-generate", response_model=InvoiceSummary, status_code=status.HTTP_201_CREATED)
async def auto_generate_invoice(
    payload: AutoGenerateInvoiceRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.auto_generate_invoice(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.get("", response_model=InvoiceListResponse)
async def search_invoices(
    branch_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    encounter_id: uuid.UUID | None = Query(None),
    status_filter: InvoiceStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceListResponse:
    return await service.search_invoices(
        tenant_id=current_user.tenant_id, branch_id=branch_id, patient_id=patient_id, encounter_id=encounter_id,
        status_filter=status_filter, actor_role=current_user.role_code, actor_user_id=current_user.user_id, limit=limit, offset=offset,
    )


@invoice_router.get("/me", response_model=InvoiceListResponse)
async def get_my_invoices(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("billing.view_own")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceListResponse:
    return await service.get_my_invoices(tenant_id=current_user.tenant_id, user_id=current_user.user_id, limit=limit, offset=offset)


@invoice_router.get("/{invoice_id}", response_model=InvoiceSummary)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.get_invoice(tenant_id=current_user.tenant_id, invoice_id=invoice_id, actor_role=current_user.role_code, actor_user_id=current_user.user_id)


@invoice_router.patch("/{invoice_id}", response_model=InvoiceSummary)
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.update_invoice(tenant_id=current_user.tenant_id, invoice_id=invoice_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.post("/{invoice_id}/line-items", response_model=InvoiceSummary, status_code=status.HTTP_201_CREATED)
async def add_line_item(
    invoice_id: uuid.UUID,
    payload: InvoiceLineItemCreateRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.add_line_item(tenant_id=current_user.tenant_id, invoice_id=invoice_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.patch("/{invoice_id}/line-items/{item_id}", response_model=InvoiceSummary)
async def update_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: InvoiceLineItemUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.update_line_item(tenant_id=current_user.tenant_id, invoice_id=invoice_id, item_id=item_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.delete("/{invoice_id}/line-items/{item_id}", response_model=InvoiceSummary)
async def delete_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.delete_line_item(tenant_id=current_user.tenant_id, invoice_id=invoice_id, item_id=item_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.post("/{invoice_id}/issue", response_model=InvoiceSummary)
async def issue_invoice(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.issue_invoice(tenant_id=current_user.tenant_id, invoice_id=invoice_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.post("/{invoice_id}/void", response_model=InvoiceSummary)
async def void_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceVoidRequest,
    current_user: CurrentUser = Depends(require_permission("billing.manage")),
    service: BillingService = Depends(get_billing_service),
) -> InvoiceSummary:
    return await service.void_invoice(tenant_id=current_user.tenant_id, invoice_id=invoice_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@invoice_router.post("/{invoice_id}/create-payment-order", response_model=PaymentOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_order(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_permission("payments.record")),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentOrderResponse:
    """Simulated gateway order/intent (§17) — see
    app/modules/billing/payment_gateway.py. Gated by `payments.record`,
    the same permission that gates actually recording a payment, since
    this is the first step of the same capability."""
    return await service.create_payment_order(tenant_id=current_user.tenant_id, invoice_id=invoice_id, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


# ---- Payments -----------------------------------------------------------------


@payment_router.post("", response_model=PaymentSummary, status_code=status.HTTP_201_CREATED)
async def record_payment(
    payload: PaymentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("payments.record")),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentSummary:
    return await service.record_payment(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@payment_router.get("", response_model=PaymentListResponse)
async def search_payments(
    invoice_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_permission("payments.record")),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentListResponse:
    return await service.search_payments(tenant_id=current_user.tenant_id, invoice_id=invoice_id, limit=limit, offset=offset)
