import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.vitals.schemas import VitalsCreateRequest


class TestVitalsCreateRequest:
    def test_accepts_a_single_reading_field(self) -> None:
        req = VitalsCreateRequest(encounter_id=uuid.uuid4(), heart_rate=72)
        assert req.heart_rate == 72

    def test_rejects_a_completely_empty_reading(self) -> None:
        with pytest.raises(ValidationError):
            VitalsCreateRequest(encounter_id=uuid.uuid4())

    def test_rejects_a_reading_with_only_notes(self) -> None:
        with pytest.raises(ValidationError):
            VitalsCreateRequest(encounter_id=uuid.uuid4(), notes="looked fine")

    @pytest.mark.parametrize("spo2", [-1, 101])
    def test_rejects_out_of_range_spo2(self, spo2: int) -> None:
        with pytest.raises(ValidationError):
            VitalsCreateRequest(encounter_id=uuid.uuid4(), spo2=spo2)

    @pytest.mark.parametrize("systolic", [10, 500])
    def test_rejects_out_of_range_systolic_bp(self, systolic: int) -> None:
        with pytest.raises(ValidationError):
            VitalsCreateRequest(encounter_id=uuid.uuid4(), systolic_bp=systolic)

    def test_rejects_zero_or_negative_weight(self) -> None:
        with pytest.raises(ValidationError):
            VitalsCreateRequest(encounter_id=uuid.uuid4(), weight_kg=0)

    def test_accepts_multiple_reading_fields_together(self) -> None:
        req = VitalsCreateRequest(encounter_id=uuid.uuid4(), weight_kg=70, height_cm=175, temperature_celsius=37.0)
        assert req.weight_kg == 70
        assert req.height_cm == 175
