"""Unit tests for the Razorpay payment gateway adapter's pure, no-DB
logic — Phase 2 (Master Handoff item 4). Order creation/refund (real
HTTP calls) are exercised in integration tests via a monkeypatched
transport, not here; this file covers only what needs no DB and no
network at all: signature verification and the subunit-conversion
helper.
"""

import hashlib
import hmac
from decimal import Decimal

import pytest

from app.modules.billing.payment_gateway import RazorpayPaymentGatewayAdapter, verify_razorpay_webhook_signature


def test_verify_razorpay_webhook_signature_accepts_a_correctly_signed_body() -> None:
    secret = "whsec_test_secret"
    body = b'{"event":"payment.captured","payload":{}}'
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_razorpay_webhook_signature(raw_body=body, signature=signature, webhook_secret=secret) is True


def test_verify_razorpay_webhook_signature_rejects_a_tampered_body() -> None:
    secret = "whsec_test_secret"
    body = b'{"event":"payment.captured","payload":{}}'
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    tampered_body = b'{"event":"payment.captured","payload":{"tampered":true}}'
    assert verify_razorpay_webhook_signature(raw_body=tampered_body, signature=signature, webhook_secret=secret) is False


def test_verify_razorpay_webhook_signature_rejects_the_wrong_secret() -> None:
    body = b'{"event":"payment.captured"}'
    signature = hmac.new(b"whsec_real", body, hashlib.sha256).hexdigest()

    assert verify_razorpay_webhook_signature(raw_body=body, signature=signature, webhook_secret="whsec_wrong") is False


@pytest.mark.parametrize(
    "amount,expected_subunits",
    [
        (Decimal("100.00"), 10000),
        (Decimal("99.99"), 9999),
        (Decimal("1"), 100),
        (Decimal("0.50"), 50),
    ],
)
def test_razorpay_amount_to_subunits(amount: Decimal, expected_subunits: int) -> None:
    assert RazorpayPaymentGatewayAdapter._to_subunits(amount) == expected_subunits
