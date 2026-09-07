"""Payment gateway adapter — PRD-ARCHITECTURE.md §17's
`PaymentGatewayAdapter` (interface) / `RazorpayAdapter` (India-first
default) / `ManualAdapter` (cash/card/UPI recorded by staff, already fully
built as `PaymentService.record_payment` — nothing here changes that
path). Only a `MockPaymentGatewayAdapter` is implemented: it simulates
creating a gateway order/intent (a fake `order_id`, `status="created"`)
with no real gateway call, no webhook, and — deliberately — no `Payment`
row written. Recording that a payment actually happened is still, and
will remain, `POST /api/v1/billing/payments` (the existing `ManualAdapter`
path) until a real gateway's webhook confirms it; this stub only covers
the "hand the frontend something to redirect/open a checkout with" half
of an online-payment flow.

Swapping in a real provider (Razorpay/Cashfree) later means implementing
`PaymentGatewayAdapter` and adding one `elif` branch to
`get_payment_gateway_adapter` — no change to `PaymentService` or its
caller. Nothing is persisted by this module today (no
`payment_gateway_orders` table) — a real integration would need one to
reconcile webhook callbacks against, but a stub that never receives a
webhook has nothing to reconcile yet.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class GatewayOrder:
    order_id: str
    status: str
    provider: str
    amount: Decimal
    currency: str


class PaymentGatewayAdapter(Protocol):
    async def create_order(self, *, amount: Decimal, currency: str, receipt: str) -> GatewayOrder: ...


class MockPaymentGatewayAdapter:
    async def create_order(self, *, amount: Decimal, currency: str, receipt: str) -> GatewayOrder:
        return GatewayOrder(order_id=f"mock_order_{uuid.uuid4().hex[:20]}", status="created", provider="mock", amount=amount, currency=currency)


def get_payment_gateway_adapter() -> PaymentGatewayAdapter:
    settings = get_settings()
    if settings.payment_gateway_provider == "mock":
        return MockPaymentGatewayAdapter()
    raise NotImplementedError(
        f"Unsupported payment gateway provider: {settings.payment_gateway_provider!r} — only 'mock' is implemented. "
        "A real provider (Razorpay/Cashfree) can be added behind this same PaymentGatewayAdapter interface "
        "without changing PaymentService."
    )
