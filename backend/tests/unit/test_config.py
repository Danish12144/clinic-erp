import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest

from app.core.config import Settings


class TestOtpStaticCode:
    def test_unset_by_default(self) -> None:
        assert Settings().otp_static_code is None

    def test_accepts_a_six_digit_code(self) -> None:
        assert Settings(otp_static_code="123456").otp_static_code == "123456"

    def test_rejects_a_code_that_is_not_six_digits(self) -> None:
        with pytest.raises(ValueError, match="otp_static_code must be exactly 6 digits"):
            Settings(otp_static_code="12345")

    def test_rejects_a_non_numeric_code(self) -> None:
        with pytest.raises(ValueError, match="otp_static_code must be exactly 6 digits"):
            Settings(otp_static_code="abcdef")
