import os
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from pydantic import ValidationError

from app.modules.emr.schemas import MedicalDocumentCreateRequest


class TestMedicalDocumentCreateRequest:
    def test_requires_a_title(self) -> None:
        with pytest.raises(ValidationError):
            MedicalDocumentCreateRequest(document_type="LAB_REPORT", title="", storage_key="s3://bucket/key")

    def test_requires_a_storage_key(self) -> None:
        with pytest.raises(ValidationError):
            MedicalDocumentCreateRequest(document_type="LAB_REPORT", title="CBC Report", storage_key="")

    def test_accepts_a_full_payload(self) -> None:
        req = MedicalDocumentCreateRequest(
            encounter_id=uuid.uuid4(), document_type="XRAY", title="Chest X-Ray", storage_key="https://cdn.example.com/x.pdf",
            mime_type="application/pdf", file_size_bytes=1024, notes="Pre-op",
        )
        assert req.document_type == "XRAY"
