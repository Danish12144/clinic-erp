import os
from datetime import date
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.pharmacy.schemas import MedicineCreateRequest, MedicineUpdateRequest, ReceiveStockRequest


class TestMedicineCreateRequest:
    def test_defaults_reorder_threshold_and_price(self) -> None:
        req = MedicineCreateRequest(name="Paracetamol")
        assert req.reorder_threshold == 0
        assert req.unit_price == Decimal("0")

    def test_requires_a_name(self) -> None:
        with pytest.raises(ValidationError):
            MedicineCreateRequest(name="")

    def test_rejects_negative_price(self) -> None:
        with pytest.raises(ValidationError):
            MedicineCreateRequest(name="x", unit_price=Decimal("-1"))

    def test_rejects_negative_reorder_threshold(self) -> None:
        with pytest.raises(ValidationError):
            MedicineCreateRequest(name="x", reorder_threshold=-1)


class TestMedicineUpdateRequest:
    def test_rejects_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            MedicineUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = MedicineUpdateRequest(is_active=False)
        assert req.is_active is False


class TestReceiveStockRequest:
    def test_requires_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            ReceiveStockRequest(batch_number="B1", expiry_date=date(2027, 1, 1), quantity=0)

    def test_accepts_a_valid_batch(self) -> None:
        req = ReceiveStockRequest(batch_number="B1", expiry_date=date(2027, 1, 1), quantity=10, cost_price=Decimal("1.50"))
        assert req.quantity == 10
