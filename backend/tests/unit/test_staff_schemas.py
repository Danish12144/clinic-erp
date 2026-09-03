import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.staff.schemas import StaffCreateRequest, StaffUpdateRequest


class TestStaffCreateRequest:
    def test_accepts_minimal_valid_payload(self) -> None:
        req = StaffCreateRequest(role_code="RECEPTIONIST", first_name="Priya", phone="+919876543210")
        assert req.role_code == "RECEPTIONIST"

    @pytest.mark.parametrize("role_code", ["RECEPTIONIST", "NURSE", "LAB_STAFF", "PHARMACY_STAFF", "OTHER_STAFF"])
    def test_accepts_every_valid_staff_role(self, role_code: str) -> None:
        req = StaffCreateRequest(role_code=role_code, first_name="X", phone="+919876543210")
        assert req.role_code == role_code

    @pytest.mark.parametrize("role_code", ["OWNER", "DOCTOR", "PATIENT", "NOT_A_ROLE"])
    def test_rejects_non_staff_role_codes(self, role_code: str) -> None:
        with pytest.raises(ValidationError):
            StaffCreateRequest(role_code=role_code, first_name="X", phone="+919876543210")

    def test_requires_email_or_phone(self) -> None:
        with pytest.raises(ValidationError):
            StaffCreateRequest(role_code="NURSE", first_name="Priya")

    @pytest.mark.parametrize("bad_phone", ["abc", "12", "++1234567890123456789", "phone number"])
    def test_rejects_malformed_phone(self, bad_phone: str) -> None:
        with pytest.raises(ValidationError):
            StaffCreateRequest(role_code="NURSE", first_name="Priya", phone=bad_phone)

    def test_requires_first_name(self) -> None:
        with pytest.raises(ValidationError):
            StaffCreateRequest(role_code="NURSE", phone="+919876543210")


class TestStaffUpdateRequest:
    def test_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            StaffUpdateRequest()

    def test_accepts_single_field_update(self) -> None:
        req = StaffUpdateRequest(designation="Front Desk Lead")
        assert req.designation == "Front Desk Lead"

    def test_has_no_role_code_field(self) -> None:
        assert "role_code" not in StaffUpdateRequest.model_fields
