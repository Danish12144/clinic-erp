import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.consultation.schemas import (
    ConsultationUpdateRequest,
    PrescriptionCreateRequest,
    PrescriptionItemCreateRequest,
)


class TestConsultationUpdateRequest:
    def test_rejects_completely_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            ConsultationUpdateRequest()

    def test_accepts_a_single_field_update(self) -> None:
        req = ConsultationUpdateRequest(diagnosis_text="Viral fever")
        assert req.diagnosis_text == "Viral fever"


class TestPrescriptionItemCreateRequest:
    def test_requires_a_medicine_name(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionItemCreateRequest(medicine_name_freetext="", prescribed_quantity=10)

    def test_requires_a_positive_quantity(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionItemCreateRequest(medicine_name_freetext="Paracetamol", prescribed_quantity=0)

    def test_accepts_a_full_item(self) -> None:
        item = PrescriptionItemCreateRequest(
            medicine_name_freetext="Paracetamol 500mg", dosage="1 tablet", frequency="BID", duration="5 days",
            route="oral", prescribed_quantity=10, instructions="After food",
        )
        assert item.route == "oral"


class TestPrescriptionCreateRequest:
    def test_requires_at_least_one_item(self) -> None:
        with pytest.raises(ValidationError):
            PrescriptionCreateRequest(encounter_id=uuid.uuid4(), items=[])

    def test_accepts_multiple_items(self) -> None:
        req = PrescriptionCreateRequest(
            encounter_id=uuid.uuid4(),
            items=[
                PrescriptionItemCreateRequest(medicine_name_freetext="A", prescribed_quantity=1),
                PrescriptionItemCreateRequest(medicine_name_freetext="B", prescribed_quantity=2),
            ],
        )
        assert len(req.items) == 2
