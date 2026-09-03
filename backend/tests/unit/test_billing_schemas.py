import os
import uuid
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.billing.schemas import (
    InvoiceLineItemCreateRequest,
    InvoiceLineItemUpdateRequest,
    InvoiceUpdateRequest,
    InvoiceVoidRequest,
    PaymentCreateRequest,
)


class TestInvoiceLineItemCreateRequest:
    def test_defaults_quantity_to_one(self) -> None:
        item = InvoiceLineItemCreateRequest(source_type="CONSULTATION", description="Consult fee", unit_price=Decimal("500"))
        assert item.quantity == Decimal("1")

    def test_rejects_zero_quantity(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceLineItemCreateRequest(source_type="OTHER", description="x", quantity=Decimal("0"), unit_price=Decimal("10"))

    def test_rejects_negative_unit_price(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceLineItemCreateRequest(source_type="OTHER", description="x", unit_price=Decimal("-1"))


class TestInvoiceUpdateRequest:
    def test_rejects_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = InvoiceUpdateRequest(discount=Decimal("50"))
        assert req.discount == Decimal("50")


class TestInvoiceLineItemUpdateRequest:
    def test_rejects_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceLineItemUpdateRequest()


class TestInvoiceVoidRequest:
    def test_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceVoidRequest(reason="")


class TestPaymentCreateRequest:
    def test_rejects_zero_amount(self) -> None:
        with pytest.raises(ValidationError):
            PaymentCreateRequest(invoice_id=uuid.uuid4(), amount=Decimal("0"), method="CASH")

    def test_accepts_a_negative_amount_as_a_refund(self) -> None:
        req = PaymentCreateRequest(invoice_id=uuid.uuid4(), amount=Decimal("-100"), method="CASH", notes="Refund")
        assert req.amount == Decimal("-100")

    def test_accepts_a_positive_payment(self) -> None:
        req = PaymentCreateRequest(invoice_id=uuid.uuid4(), amount=Decimal("500"), method="UPI")
        assert req.amount == Decimal("500")
