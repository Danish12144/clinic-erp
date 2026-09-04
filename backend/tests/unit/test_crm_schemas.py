import os
import uuid
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.crm.schemas import FollowUpCreateRequest


class TestFollowUpCreateRequest:
    def test_defaults_channel_to_whatsapp(self) -> None:
        req = FollowUpCreateRequest(patient_id=uuid.uuid4(), due_at=datetime.now(timezone.utc))
        assert req.channel == "WHATSAPP"

    def test_doctor_and_encounter_are_optional(self) -> None:
        req = FollowUpCreateRequest(patient_id=uuid.uuid4(), due_at=datetime.now(timezone.utc))
        assert req.doctor_id is None
        assert req.encounter_id is None

    def test_rejects_an_overly_long_reason(self) -> None:
        with pytest.raises(ValidationError):
            FollowUpCreateRequest(patient_id=uuid.uuid4(), due_at=datetime.now(timezone.utc), reason="x" * 1001)
