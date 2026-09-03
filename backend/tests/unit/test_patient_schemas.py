import os
from datetime import date, timedelta

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.patients.schemas import EmergencyContact, PatientCreateRequest, PatientUpdateRequest


class TestPatientCreateRequest:
    def test_accepts_minimal_valid_payload(self) -> None:
        req = PatientCreateRequest(first_name="Asha", phone="+919876543210")
        assert req.first_name == "Asha"
        assert req.mrn is None

    def test_requires_phone_or_email(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(first_name="Asha")

    def test_email_alone_is_sufficient(self) -> None:
        req = PatientCreateRequest(first_name="Asha", email="asha@example.com")
        assert req.email == "asha@example.com"

    @pytest.mark.parametrize("bad_phone", ["abc", "12", "++1234567890123456789", "phone number"])
    def test_rejects_malformed_phone(self, bad_phone: str) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(first_name="Asha", phone=bad_phone)

    def test_rejects_future_date_of_birth(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(first_name="Asha", phone="+919876543210", date_of_birth=date.today() + timedelta(days=1))

    def test_rejects_implausibly_old_date_of_birth(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(
                first_name="Asha", phone="+919876543210", date_of_birth=date.today() - timedelta(days=200 * 365)
            )

    def test_accepts_reasonable_date_of_birth(self) -> None:
        req = PatientCreateRequest(
            first_name="Asha", phone="+919876543210", date_of_birth=date.today() - timedelta(days=30 * 365)
        )
        assert req.date_of_birth is not None

    @pytest.mark.parametrize("bad_mrn", ["ab", "has space", "has/slash", ""])
    def test_rejects_malformed_explicit_mrn(self, bad_mrn: str) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(first_name="Asha", phone="+919876543210", mrn=bad_mrn)

    def test_accepts_well_formed_explicit_mrn(self) -> None:
        req = PatientCreateRequest(first_name="Asha", phone="+919876543210", mrn="MRN-2026-0001")
        assert req.mrn == "MRN-2026-0001"

    def test_rejects_invalid_gender(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest.model_validate(
                {"first_name": "Asha", "phone": "+919876543210", "gender": "Unspecified"}
            )

    def test_rejects_invalid_blood_group(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest.model_validate({"first_name": "Asha", "phone": "+919876543210", "blood_group": "X+"})

    def test_allergies_are_trimmed_and_empty_strings_dropped(self) -> None:
        req = PatientCreateRequest(
            first_name="Asha", phone="+919876543210", allergies=["  Penicillin  ", "", "   ", "Peanuts"]
        )
        assert req.allergies == ["Penicillin", "Peanuts"]

    def test_rejects_too_many_allergy_entries(self) -> None:
        with pytest.raises(ValidationError):
            PatientCreateRequest(first_name="Asha", phone="+919876543210", allergies=[f"item-{i}" for i in range(51)])

    def test_emergency_contact_requires_all_fields(self) -> None:
        with pytest.raises(ValidationError):
            EmergencyContact.model_validate({"name": "Rahul"})

    def test_emergency_contact_valid(self) -> None:
        contact = EmergencyContact(name="Rahul Sharma", phone="+919876500000", relationship="Spouse")
        assert contact.relationship == "Spouse"


class TestPatientUpdateRequest:
    def test_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            PatientUpdateRequest()

    def test_accepts_single_field_update(self) -> None:
        req = PatientUpdateRequest(phone="+919876543210")
        assert req.phone == "+919876543210"

    def test_allows_clearing_allergies_to_empty_list(self) -> None:
        req = PatientUpdateRequest(allergies=[])
        assert req.allergies == []

    def test_does_not_require_phone_or_email(self) -> None:
        # Unlike create — an existing patient shouldn't be forced to
        # backfill contact info just to update an unrelated field like
        # blood_group.
        req = PatientUpdateRequest(blood_group="O+")
        assert req.blood_group == "O+"
