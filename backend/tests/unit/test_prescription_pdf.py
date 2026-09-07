import os
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

from app.modules.consultation.pdf import PrescriptionPdfItem, render_prescription_pdf
from app.modules.letterhead.schemas import LetterheadPrintMode, LetterheadResolved, ResolvedHeaderFooter

_ITEM = PrescriptionPdfItem(
    medicine_name="Paracetamol 500mg", dosage="1 tablet", frequency="TID", duration="5 days",
    route="Oral", prescribed_quantity=15, instructions="After food",
)


def _digital_letterhead(**overrides) -> LetterheadResolved:
    header = ResolvedHeaderFooter(source="AUTO", clinic_name="Sunrise Clinic", address="123 Main St", contact="+91-9999999999", branch_name="Main Branch")
    footer = ResolvedHeaderFooter(source="AUTO", clinic_name="Sunrise Clinic", address=None, contact="+91-9999999999")
    defaults = dict(mode=LetterheadPrintMode.DIGITAL, header=header, footer=footer, top_margin_mm=0.0, bottom_margin_mm=0.0)
    defaults.update(overrides)
    return LetterheadResolved(**defaults)


class TestRenderPrescriptionPdf:
    def test_returns_valid_pdf_bytes(self) -> None:
        pdf_bytes = render_prescription_pdf(
            patient_name="Jane Doe", doctor_name="Dr. Smith", issued_at=datetime.now(timezone.utc),
            items=[_ITEM], letterhead=_digital_letterhead(),
        )
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 100

    def test_renders_with_no_header_or_footer(self) -> None:
        letterhead = LetterheadResolved(mode=LetterheadPrintMode.PHYSICAL, header=None, footer=None, top_margin_mm=40.0, bottom_margin_mm=20.0)
        pdf_bytes = render_prescription_pdf(patient_name="John", doctor_name="Dr. X", issued_at=datetime.now(timezone.utc), items=[_ITEM], letterhead=letterhead)
        assert pdf_bytes.startswith(b"%PDF")

    def test_renders_with_multiple_items_and_missing_optional_fields(self) -> None:
        sparse_item = PrescriptionPdfItem(medicine_name="Ibuprofen", dosage=None, frequency=None, duration=None, route=None, prescribed_quantity=10, instructions=None)
        pdf_bytes = render_prescription_pdf(
            patient_name="Multi Item", doctor_name="Dr. Y", issued_at=datetime.now(timezone.utc),
            items=[_ITEM, sparse_item], letterhead=_digital_letterhead(),
        )
        assert pdf_bytes.startswith(b"%PDF")

    def test_renders_with_an_empty_item_list(self) -> None:
        pdf_bytes = render_prescription_pdf(patient_name="NoItems", doctor_name="Dr. Z", issued_at=datetime.now(timezone.utc), items=[], letterhead=_digital_letterhead())
        assert pdf_bytes.startswith(b"%PDF")
