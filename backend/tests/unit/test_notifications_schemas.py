import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.notifications.schemas import (
    NotificationTemplateCreateRequest,
    NotificationTemplateUpdateRequest,
    SendPreviewRequest,
)


class TestNotificationTemplateCreateRequest:
    def test_accepts_a_valid_payload(self) -> None:
        req = NotificationTemplateCreateRequest(
            template_key="APPOINTMENT_BOOKED", channel="WHATSAPP",
            body_text="Hi {{patient_name}}, your appointment is booked.", variables=["patient_name"],
        )
        assert req.template_key == "APPOINTMENT_BOOKED"
        assert req.is_active is True

    def test_defaults_variables_to_an_empty_list(self) -> None:
        req = NotificationTemplateCreateRequest(template_key="CUSTOM_KEY", channel="SMS", body_text="Hello.")
        assert req.variables == []

    def test_accepts_a_custom_non_exhaustive_template_key(self) -> None:
        # template_key is deliberately open/free-text, not a closed enum.
        req = NotificationTemplateCreateRequest(template_key="BIRTHDAY_GREETING", channel="EMAIL", body_text="Happy birthday!")
        assert req.template_key == "BIRTHDAY_GREETING"

    def test_rejects_an_invalid_channel(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateCreateRequest(template_key="X", channel="FAX", body_text="Hello.")

    def test_rejects_an_empty_body_text(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateCreateRequest(template_key="X", channel="SMS", body_text="")

    def test_rejects_an_empty_variable_name(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateCreateRequest(template_key="X", channel="SMS", body_text="Hi", variables=[""])

    def test_rejects_too_many_variables(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateCreateRequest(template_key="X", channel="SMS", body_text="Hi", variables=[f"v{i}" for i in range(31)])


class TestNotificationTemplateUpdateRequest:
    def test_rejects_an_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = NotificationTemplateUpdateRequest(is_active=False)
        assert req.is_active is False
        assert "is_active" in req.model_fields_set
        assert "body_text" not in req.model_fields_set

    def test_channel_and_template_key_are_not_updatable_fields(self) -> None:
        # There is no `channel`/`template_key` field on the update schema
        # at all — identity fields stay immutable after creation.
        assert "channel" not in NotificationTemplateUpdateRequest.model_fields
        assert "template_key" not in NotificationTemplateUpdateRequest.model_fields

    def test_rejects_an_empty_variable_name_on_update(self) -> None:
        with pytest.raises(ValidationError):
            NotificationTemplateUpdateRequest(variables=["ok", ""])


class TestSendPreviewRequest:
    def test_accepts_a_minimal_payload(self) -> None:
        template_id = uuid.uuid4()
        req = SendPreviewRequest(template_id=template_id)
        assert req.template_id == template_id
        assert req.sample_data == {}

    def test_accepts_sample_data(self) -> None:
        req = SendPreviewRequest(template_id=uuid.uuid4(), sample_data={"patient_name": "Jane Doe"})
        assert req.sample_data["patient_name"] == "Jane Doe"
