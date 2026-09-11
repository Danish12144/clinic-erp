import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.appointments.schemas import (
    AppointmentCancelRequest,
    AppointmentRescheduleRequest,
    MyAppointmentCreateRequest,
)

_FUTURE = datetime.now(timezone.utc) + timedelta(days=2)
_PAST = datetime.now(timezone.utc) - timedelta(days=2)
_JUST_NOW = datetime.now(timezone.utc) - timedelta(minutes=1)
_WELL_PAST_GRACE = datetime.now(timezone.utc) - timedelta(minutes=10)


class TestMyAppointmentCreateRequest:
    def test_accepts_valid_future_appointment(self) -> None:
        req = MyAppointmentCreateRequest(branch_id=uuid.uuid4(), doctor_id=uuid.uuid4(), scheduled_at=_FUTURE)
        assert req.duration_minutes == 15

    def test_rejects_past_scheduled_at(self) -> None:
        with pytest.raises(ValidationError):
            MyAppointmentCreateRequest(branch_id=uuid.uuid4(), doctor_id=uuid.uuid4(), scheduled_at=_PAST)

    def test_accepts_a_moment_ago_within_the_grace_window(self) -> None:
        # An instant/same-day booking submitted for "right now" can already
        # read as a few seconds/minutes in the past by the time it reaches
        # this validator (client clock skew, network latency) — a 5-minute
        # grace window absorbs that instead of 422ing a legitimate booking.
        req = MyAppointmentCreateRequest(branch_id=uuid.uuid4(), doctor_id=uuid.uuid4(), scheduled_at=_JUST_NOW)
        assert req.scheduled_at == _JUST_NOW

    def test_rejects_a_datetime_well_past_the_grace_window(self) -> None:
        with pytest.raises(ValidationError):
            MyAppointmentCreateRequest(branch_id=uuid.uuid4(), doctor_id=uuid.uuid4(), scheduled_at=_WELL_PAST_GRACE)

    def test_rejects_naive_datetime_without_timezone(self) -> None:
        with pytest.raises(ValidationError):
            MyAppointmentCreateRequest.model_validate(
                {"branch_id": str(uuid.uuid4()), "doctor_id": str(uuid.uuid4()), "scheduled_at": "2099-01-01T10:00:00"}
            )

    @pytest.mark.parametrize("duration", [1, 4, 241, 300])
    def test_rejects_out_of_range_duration(self, duration: int) -> None:
        with pytest.raises(ValidationError):
            MyAppointmentCreateRequest(branch_id=uuid.uuid4(), doctor_id=uuid.uuid4(), scheduled_at=_FUTURE, duration_minutes=duration)


class TestAppointmentRescheduleRequest:
    def test_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            AppointmentRescheduleRequest()

    def test_accepts_single_field_update(self) -> None:
        req = AppointmentRescheduleRequest(duration_minutes=30)
        assert req.duration_minutes == 30

    def test_rejects_past_scheduled_at(self) -> None:
        with pytest.raises(ValidationError):
            AppointmentRescheduleRequest(scheduled_at=_PAST)


class TestAppointmentCancelRequest:
    def test_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError):
            AppointmentCancelRequest(reason="")

    def test_accepts_a_reason(self) -> None:
        req = AppointmentCancelRequest(reason="Patient requested cancellation")
        assert req.reason == "Patient requested cancellation"
