import os
from decimal import Decimal

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.doctors.schemas import DoctorCreateRequest, DoctorUpdateRequest


class TestDoctorCreateRequest:
    def test_accepts_minimal_valid_payload(self) -> None:
        req = DoctorCreateRequest(first_name="Rakesh", phone="+919876543210")
        assert req.first_name == "Rakesh"
        assert req.branch_ids == []

    def test_requires_email_or_phone(self) -> None:
        with pytest.raises(ValidationError):
            DoctorCreateRequest(first_name="Rakesh")

    def test_email_alone_is_sufficient(self) -> None:
        req = DoctorCreateRequest(first_name="Rakesh", email="rakesh@example.com")
        assert req.email == "rakesh@example.com"

    @pytest.mark.parametrize("bad_phone", ["abc", "12", "++1234567890123456789", "phone number"])
    def test_rejects_malformed_phone(self, bad_phone: str) -> None:
        with pytest.raises(ValidationError):
            DoctorCreateRequest(first_name="Rakesh", phone=bad_phone)

    def test_rejects_negative_consultation_fee(self) -> None:
        with pytest.raises(ValidationError):
            DoctorCreateRequest(first_name="Rakesh", phone="+919876543210", consultation_fee=Decimal("-1"))

    def test_accepts_valid_consultation_fee(self) -> None:
        req = DoctorCreateRequest(first_name="Rakesh", phone="+919876543210", consultation_fee=Decimal("500.00"))
        assert req.consultation_fee == Decimal("500.00")

    def test_accepts_working_hours(self) -> None:
        req = DoctorCreateRequest(
            first_name="Rakesh",
            phone="+919876543210",
            working_hours={"mon": {"open": "09:00", "close": "17:00"}},
        )
        assert req.working_hours.mon is not None
        assert req.working_hours.mon.open == "09:00"

    def test_requires_first_name(self) -> None:
        with pytest.raises(ValidationError):
            DoctorCreateRequest(phone="+919876543210")


class TestDoctorUpdateRequest:
    def test_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            DoctorUpdateRequest()

    def test_accepts_single_field_update(self) -> None:
        req = DoctorUpdateRequest(specialization="Cardiology")
        assert req.specialization == "Cardiology"

    def test_rejects_negative_consultation_fee(self) -> None:
        with pytest.raises(ValidationError):
            DoctorUpdateRequest(consultation_fee=Decimal("-50"))
