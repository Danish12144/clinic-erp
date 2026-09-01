import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.auth.schemas import OtpVerifyPayload, StaffLoginRequest


def test_otp_verify_rejects_non_numeric_code() -> None:
    with pytest.raises(ValidationError):
        OtpVerifyPayload(clinic_slug="apex", phone="+919876543210", code="abcdef")


def test_otp_verify_rejects_wrong_length_code() -> None:
    with pytest.raises(ValidationError):
        OtpVerifyPayload(clinic_slug="apex", phone="+919876543210", code="12345")


def test_otp_verify_accepts_six_digit_code() -> None:
    payload = OtpVerifyPayload(clinic_slug="apex", phone="+919876543210", code="123456")
    assert payload.code == "123456"


def test_staff_login_requires_non_empty_password() -> None:
    with pytest.raises(ValidationError):
        StaffLoginRequest(clinic_slug="apex", identifier="owner@apex.clinic", password="")


def test_staff_login_requires_clinic_slug() -> None:
    with pytest.raises(ValidationError):
        StaffLoginRequest(clinic_slug="", identifier="owner@apex.clinic", password="secret123")
