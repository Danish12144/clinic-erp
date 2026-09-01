import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.tenancy.schemas import (
    BranchCreateRequest,
    BranchUpdateRequest,
    ClinicUpdateRequest,
    DayHours,
    WorkingHours,
    validate_setting_key,
)


class TestDayHours:
    def test_accepts_valid_hh_mm(self) -> None:
        hours = DayHours(open="09:00", close="18:00")
        assert hours.open == "09:00"
        assert hours.close == "18:00"

    @pytest.mark.parametrize("bad_time", ["9:00", "09:60", "24:00", "9am", "09-00", ""])
    def test_rejects_malformed_time(self, bad_time: str) -> None:
        with pytest.raises(ValidationError):
            DayHours(open=bad_time, close="18:00")

    def test_rejects_close_before_or_equal_to_open(self) -> None:
        with pytest.raises(ValidationError):
            DayHours(open="18:00", close="09:00")
        with pytest.raises(ValidationError):
            DayHours(open="09:00", close="09:00")


class TestWorkingHours:
    def test_all_days_optional(self) -> None:
        hours = WorkingHours()
        assert hours.mon is None

    def test_rejects_unknown_day_key(self) -> None:
        with pytest.raises(ValidationError):
            WorkingHours.model_validate({"funday": {"open": "09:00", "close": "18:00"}})

    def test_accepts_a_subset_of_days(self) -> None:
        hours = WorkingHours.model_validate({"mon": {"open": "09:00", "close": "17:00"}})
        assert hours.mon is not None
        assert hours.mon.open == "09:00"
        assert hours.tue is None


class TestClinicUpdateRequest:
    def test_accepts_valid_iana_timezone(self) -> None:
        req = ClinicUpdateRequest(timezone="Asia/Kolkata")
        assert req.timezone == "Asia/Kolkata"

    def test_rejects_unknown_timezone(self) -> None:
        with pytest.raises(ValidationError):
            ClinicUpdateRequest(timezone="Mars/Olympus_Mons")

    def test_accepts_valid_locale(self) -> None:
        req = ClinicUpdateRequest(locale="en-IN")
        assert req.locale == "en-IN"

    @pytest.mark.parametrize("bad_locale", ["en_IN", "english", "EN-in", "en-india"])
    def test_rejects_malformed_locale(self, bad_locale: str) -> None:
        with pytest.raises(ValidationError):
            ClinicUpdateRequest(locale=bad_locale)

    def test_accepts_valid_gstin(self) -> None:
        req = ClinicUpdateRequest(gst_number="27AAPFU0939F1ZV")
        assert req.gst_number == "27AAPFU0939F1ZV"

    @pytest.mark.parametrize("bad_gstin", ["not-a-gstin", "27AAPFU0939F1Z", "123456789012345"])
    def test_rejects_malformed_gstin(self, bad_gstin: str) -> None:
        with pytest.raises(ValidationError):
            ClinicUpdateRequest(gst_number=bad_gstin)

    def test_rejects_empty_update_with_no_fields(self) -> None:
        with pytest.raises(ValidationError):
            ClinicUpdateRequest()

    def test_slug_and_status_are_not_fields(self) -> None:
        # Deliberately excluded from the update schema — see the schema's
        # own docstring for why (login/subdomain resolution, billing
        # lifecycle respectively).
        assert "slug" not in ClinicUpdateRequest.model_fields
        assert "status" not in ClinicUpdateRequest.model_fields


class TestBranchSchemas:
    def test_create_request_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            BranchCreateRequest(name="")

    def test_create_request_defaults_working_hours_to_empty(self) -> None:
        req = BranchCreateRequest(name="Main Branch")
        assert req.working_hours.mon is None

    def test_create_request_rejects_unknown_timezone(self) -> None:
        with pytest.raises(ValidationError):
            BranchCreateRequest(name="Main Branch", timezone="Nowhere/Fake")

    def test_update_request_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            BranchUpdateRequest()

    def test_update_request_accepts_just_is_active(self) -> None:
        req = BranchUpdateRequest(is_active=False)
        assert req.is_active is False


class TestSettingKeyValidation:
    @pytest.mark.parametrize(
        "good_key", ["branding", "branding.primary_color", "defaults.consultation_fee", "a.b.c"]
    )
    def test_accepts_well_formed_keys(self, good_key: str) -> None:
        assert validate_setting_key(good_key) == good_key

    @pytest.mark.parametrize(
        "bad_key", ["", "Branding", "branding..color", ".branding", "branding.", "branding color", "branding-color"]
    )
    def test_rejects_malformed_keys(self, bad_key: str) -> None:
        with pytest.raises(ValueError):
            validate_setting_key(bad_key)
