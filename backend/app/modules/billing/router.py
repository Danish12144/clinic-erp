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

Phase 1 (migration 0032) added `billing.view` — tenant-wide, read-only,
unscoped like `billing.manage` rather than row-scoped like
`billing.view_own` (BillingService's row-scoping is keyed on
`actor_role`, never on which permission let the caller through) — for a
finance/accounts persona granted it via a per-user permission override,
not a new role. It's in `_READ_PERMS` alongside the other two, and also
widens the standalone payments-list route below.

The static `/me` route is declared before `/{invoice_id}` so FastAPI
matches it first, same reasoning as Appointments' `/me` routes.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response

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
from app.modules.billing.webhook_service import PaymentGatewayWebhookService

invoice_router = APIRouter(prefix="/api/v1/billing/invoices", tags=["billing:invoices"])
payment_router = APIRouter(prefix="/api/v1/billing/payments", tags=["billing:payments"])
webhook_router = APIRouter(prefix="/api/v1/billing/webhooks", tags=["billing:webhooks"])

_READ_PERMS = ("billing.manage", "billing.view_own", "billing.view")


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


@invoice_router.get("/export", response_class=Response)
async def export_invoices_csv(
    branch_id: uuid.UUID | None = Query(None),
    patient_id: uuid.UUID | None = Query(None),
    encounter_id: uuid.UUID | None = Query(None),
    status_filter: InvoiceStatus | None = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_PERMS)),
    service: BillingService = Depends(get_billing_service),
) -> Response:
    """Phase 1 (Master Handoff item 6) — same filters and row-scoping as
    `search_invoices`, just serialized as a CSV file instead of JSON.
    Declared before `/{invoice_id}` so FastAPI matches this static path
    first, same reasoning as the `/me` route below."""
    csv_body = await service.export_invoices_csv(
        tenant_id=current_user.tenant_id, branch_id=branch_id, patient_id=patient_id, encounter_id=encounter_id,
        status_filter=status_filter, actor_role=current_user.role_code, actor_user_id=current_user.user_id,
    )
    return Response(
        content=csv_body, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices.csv"},
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
    # Also open to billing.view (Phase 1 Accountant bundle, migration
    # 0032) — a finance user reconciling collected money across every
    # invoice at once is the more useful shape of this endpoint for them
    # than the per-invoice nested `payments` on InvoiceSummary.
    current_user: CurrentUser = Depends(require_any_permission("payments.record", "billing.view")),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentListResponse:
    return await service.search_payments(tenant_id=current_user.tenant_id, invoice_id=invoice_id, limit=limit, offset=offset)


# ---- Payment gateway webhooks ---------------------------------------------------


def get_webhook_service() -> PaymentGatewayWebhookService:
    return PaymentGatewayWebhookService()


@webhook_router.post("/razorpay", status_code=status.HTTP_200_OK)
async def razorpay_webhook(request: Request, service: PaymentGatewayWebhookService = Depends(get_webhook_service)) -> dict[str, str]:
    """Phase 2 (Master Handoff item 4) — no auth dependency at all, by
    design: Razorpay calls this directly with no JWT, authenticating
    itself only via the `X-Razorpay-Signature` HMAC header, verified
    against the raw request body inside the service (see
    `verify_razorpay_webhook_signature`'s own docstring for why it must be
    the raw bytes, not a re-parsed body)."""
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    payload = await request.json()
    await service.process_razorpay_webhook(raw_body=raw_body, signature=signature, payload=payload)
    return {"status": "ok"}
