import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.leads.schemas import (
    LeadConvertRequest,
    LeadCreateRequest,
    LeadInteractionCreateRequest,
    LeadUpdateRequest,
)


class TestLeadCreateRequest:
    def test_accepts_a_minimal_payload(self) -> None:
        req = LeadCreateRequest(first_name="Jane")
        assert req.first_name == "Jane"
        assert req.last_name is None
        assert req.source is None

    def test_accepts_a_full_payload(self) -> None:
        assigned_to = uuid.uuid4()
        req = LeadCreateRequest(
            first_name="Jane", last_name="Doe", phone="+919876543210", email="jane@example.com",
            source="WEBSITE", assigned_to_user_id=assigned_to, notes="Interested in dental checkup",
        )
        assert req.source == "WEBSITE"
        assert req.assigned_to_user_id == assigned_to

    def test_rejects_a_blank_first_name(self) -> None:
        with pytest.raises(ValidationError):
            LeadCreateRequest(first_name="")

    def test_rejects_an_invalid_source(self) -> None:
        with pytest.raises(ValidationError):
            LeadCreateRequest(first_name="Jane", source="COLD_CALL")

    def test_rejects_an_invalid_phone(self) -> None:
        with pytest.raises(ValidationError):
            LeadCreateRequest(first_name="Jane", phone="not-a-phone")

    def test_rejects_an_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            LeadCreateRequest(first_name="Jane", email="not-an-email")


class TestLeadUpdateRequest:
    def test_rejects_an_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            LeadUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = LeadUpdateRequest(status="CONTACTED")
        assert req.status == "CONTACTED"
        assert "status" in req.model_fields_set
        assert "notes" not in req.model_fields_set

    def test_rejects_an_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            LeadUpdateRequest(status="QUALIFIED")

    def test_accepts_reassignment(self) -> None:
        new_assignee = uuid.uuid4()
        req = LeadUpdateRequest(assigned_to_user_id=new_assignee)
        assert req.assigned_to_user_id == new_assignee


class TestLeadInteractionCreateRequest:
    def test_accepts_a_minimal_payload(self) -> None:
        req = LeadInteractionCreateRequest(interaction_type="CALL")
        assert req.interaction_type == "CALL"
        assert req.outcome is None

    def test_accepts_a_full_payload(self) -> None:
        req = LeadInteractionCreateRequest(interaction_type="WHATSAPP", outcome="No response", notes="Sent brochure")
        assert req.outcome == "No response"

    def test_rejects_an_invalid_interaction_type(self) -> None:
        with pytest.raises(ValidationError):
            LeadInteractionCreateRequest(interaction_type="SMS")


class TestLeadConvertRequest:
    def test_accepts_an_empty_payload(self) -> None:
        req = LeadConvertRequest()
        assert req.gender is None
        assert req.date_of_birth is None
        assert req.address is None

    def test_accepts_optional_clinical_fields(self) -> None:
        req = LeadConvertRequest(gender="Female", date_of_birth="1990-05-01", address="12 Main St")
        assert req.gender == "Female"
        assert req.address == "12 Main St"

    def test_rejects_an_invalid_gender(self) -> None:
        with pytest.raises(ValidationError):
            LeadConvertRequest(gender="Unknown")
