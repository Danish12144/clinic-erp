import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.checkin.schemas import EncounterCancelRequest, QueueStatusUpdateRequest, WalkInRequest


class TestWalkInRequest:
    def test_doctor_id_is_optional(self) -> None:
        req = WalkInRequest(patient_id=uuid.uuid4(), branch_id=uuid.uuid4())
        assert req.doctor_id is None

    def test_accepts_a_doctor_id(self) -> None:
        doctor_id = uuid.uuid4()
        req = WalkInRequest(patient_id=uuid.uuid4(), branch_id=uuid.uuid4(), doctor_id=doctor_id)
        assert req.doctor_id == doctor_id


class TestEncounterCancelRequest:
    def test_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            EncounterCancelRequest(reason="")

    def test_accepts_a_reason(self) -> None:
        req = EncounterCancelRequest(reason="Wrong patient checked in")
        assert req.reason == "Wrong patient checked in"


class TestQueueStatusUpdateRequest:
    def test_accepts_a_valid_status(self) -> None:
        req = QueueStatusUpdateRequest(status="CALLED")
        assert req.status.value == "CALLED"

    def test_rejects_an_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            QueueStatusUpdateRequest(status="BOGUS")
