import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.lab.schemas import LabResultCreateRequest, LabTestUpdateRequest, ReferenceRangeEntry


class TestReferenceRangeEntry:
    def test_accepts_a_valid_entry(self) -> None:
        entry = ReferenceRangeEntry(min=4.0, max=10.0, unit="10^3/uL")
        assert entry.max == 10.0

    def test_rejects_an_invalid_sex_value(self) -> None:
        with pytest.raises(ValidationError):
            ReferenceRangeEntry(sex="Unknown")

    def test_accepts_an_entry_with_no_bounds_set(self) -> None:
        entry = ReferenceRangeEntry()
        assert entry.min is None and entry.max is None


class TestLabTestUpdateRequest:
    def test_rejects_empty_payload(self) -> None:
        with pytest.raises(ValidationError):
            LabTestUpdateRequest()

    def test_accepts_a_single_field(self) -> None:
        req = LabTestUpdateRequest(is_active=False)
        assert req.is_active is False


class TestLabResultCreateRequest:
    def test_requires_at_least_one_result(self) -> None:
        with pytest.raises(ValidationError):
            LabResultCreateRequest(results=[])

    def test_accepts_multiple_results(self) -> None:
        req = LabResultCreateRequest(results=[{"parameter": "TSH", "value": "2.1"}, {"parameter": "T3", "value": "1.2"}])
        assert len(req.results) == 2
