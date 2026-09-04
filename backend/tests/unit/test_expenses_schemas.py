import os
import uuid
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.expenses.schemas import ExpenseCreateRequest, ExpenseUpdateRequest


class TestExpenseCreateRequest:
    def test_accepts_a_valid_payload(self) -> None:
        req = ExpenseCreateRequest(
            branch_id=uuid.uuid4(), category="RENT", amount=Decimal("1500.00"), payment_mode="CASH",
        )
        assert req.amount == Decimal("1500.00")
        assert req.expense_date is None  # defaulted server-side, not here

    def test_rejects_a_zero_amount(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreateRequest(branch_id=uuid.uuid4(), category="RENT", amount=Decimal("0"), payment_mode="CASH")

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreateRequest(branch_id=uuid.uuid4(), category="RENT", amount=Decimal("-10.00"), payment_mode="CASH")

    def test_rejects_more_than_two_decimal_places(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreateRequest(branch_id=uuid.uuid4(), category="RENT", amount=Decimal("10.005"), payment_mode="CASH")

    def test_rejects_an_invalid_category(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreateRequest(branch_id=uuid.uuid4(), category="BRIBES", amount=Decimal("10.00"), payment_mode="CASH")

    def test_rejects_an_invalid_payment_mode(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseCreateRequest(branch_id=uuid.uuid4(), category="RENT", amount=Decimal("10.00"), payment_mode="CHEQUE")

    def test_vendor_and_notes_are_optional(self) -> None:
        req = ExpenseCreateRequest(branch_id=uuid.uuid4(), category="OTHER", amount=Decimal("5.00"), payment_mode="UPI")
        assert req.vendor is None
        assert req.notes is None


class TestExpenseUpdateRequest:
    def test_rejects_an_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = ExpenseUpdateRequest(amount=Decimal("99.99"))
        assert req.amount == Decimal("99.99")
        assert "amount" in req.model_fields_set
        assert "category" not in req.model_fields_set

    def test_rejects_a_zero_amount(self) -> None:
        with pytest.raises(ValidationError):
            ExpenseUpdateRequest(amount=Decimal("0"))
