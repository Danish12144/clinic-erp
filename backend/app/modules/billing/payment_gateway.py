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

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


@dataclass(frozen=True)
class GatewayOrder:
    order_id: str
    status: str
    provider: str
    amount: Decimal
    currency: str


@dataclass(frozen=True)
class GatewayRefund:
    refund_id: str
    status: str
    amount: Decimal


class PaymentGatewayAdapter(Protocol):
    async def create_order(self, *, amount: Decimal, currency: str, receipt: str) -> GatewayOrder: ...

    async def refund(self, *, provider_payment_id: str, amount: Decimal) -> GatewayRefund: ...


class MockPaymentGatewayAdapter:
    async def create_order(self, *, amount: Decimal, currency: str, receipt: str) -> GatewayOrder:
        return GatewayOrder(order_id=f"mock_order_{uuid.uuid4().hex[:20]}", status="created", provider="mock", amount=amount, currency=currency)

    async def refund(self, *, provider_payment_id: str, amount: Decimal) -> GatewayRefund:
        return GatewayRefund(refund_id=f"mock_refund_{uuid.uuid4().hex[:20]}", status="processed", amount=amount)


class RazorpayPaymentGatewayAdapter:
    """Phase 2 (Master Handoff item 4) — a genuine Razorpay Orders/Refunds
    integration over their documented REST API (no SDK dependency added;
    both endpoints are simple JSON-over-HTTPS with HTTP Basic Auth using
    the key id/secret as username/password, exactly as Razorpay's own docs
    specify). Order creation is the "hand the frontend something to open
    Razorpay Checkout with" half of the flow — the actual money only moves
    once the gateway calls back via `PaymentGatewayWebhookService`
    (`payment.captured`/`payment.failed`), never from this class's return
    value alone."""

    _BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str) -> None:
        self._key_id = key_id
        self._key_secret = key_secret

    @staticmethod
    def _to_subunits(amount: Decimal) -> int:
        # Razorpay amounts are in the smallest currency unit (paise for
        # INR, cents for USD, ...) — always an integer, never a decimal.
        return int((amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

    async def create_order(self, *, amount: Decimal, currency: str, receipt: str) -> GatewayOrder:
        async with httpx.AsyncClient(auth=(self._key_id, self._key_secret), timeout=15.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/orders",
                json={
                    "amount": self._to_subunits(amount),
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Razorpay order creation failed: {response.status_code} {response.text}"
            )
        data = response.json()
        return GatewayOrder(order_id=data["id"], status=data["status"], provider="razorpay", amount=amount, currency=currency)

    async def refund(self, *, provider_payment_id: str, amount: Decimal) -> GatewayRefund:
        async with httpx.AsyncClient(auth=(self._key_id, self._key_secret), timeout=15.0) as client:
            response = await client.post(
                f"{self._BASE_URL}/payments/{provider_payment_id}/refund",
                json={"amount": self._to_subunits(amount)},
            )
        if response.status_code >= 400:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, f"Razorpay refund failed: {response.status_code} {response.text}"
            )
        data = response.json()
        return GatewayRefund(refund_id=data["id"], status=data.get("status", "processed"), amount=amount)


def verify_razorpay_webhook_signature(*, raw_body: bytes, signature: str, webhook_secret: str) -> bool:
    """Razorpay signs every webhook delivery with HMAC-SHA256 of the exact
    raw request body, using a merchant-configured `webhook_secret` (set
    once in the Razorpay dashboard, distinct from `key_secret`), sent in
    the `X-Razorpay-Signature` header. Must be computed over the raw bytes
    — not a re-serialized/re-parsed JSON body, which is not guaranteed to
    produce byte-identical output — and compared with a constant-time
    comparison so a timing attack can't be used to guess the signature
    byte-by-byte."""
    expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def get_payment_gateway_adapter() -> PaymentGatewayAdapter:
    settings = get_settings()
    if settings.payment_gateway_provider == "mock":
        return MockPaymentGatewayAdapter()
    if settings.payment_gateway_provider == "razorpay":
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise RuntimeError(
                "PAYMENT_GATEWAY_PROVIDER=razorpay requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to be set — "
                "misconfigured environment, failing loud rather than silently falling back to a fake gateway."
            )
        return RazorpayPaymentGatewayAdapter(key_id=settings.razorpay_key_id, key_secret=settings.razorpay_key_secret)
    raise NotImplementedError(
        f"Unsupported payment gateway provider: {settings.payment_gateway_provider!r} — only 'mock'/'razorpay' are "
        "implemented. A different provider (Cashfree/PayU) can be added behind this same PaymentGatewayAdapter "
        "interface without changing PaymentService."
    )
