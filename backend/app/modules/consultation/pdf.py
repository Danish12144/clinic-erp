"""Prescription PDF rendering — PRD-ARCHITECTURE.md §15 ("prescription PDFs
generated from `Prescription` for print/WhatsApp share"), the one concrete
piece of that promise this backend never actually built until now (the
existing `GET /api/v1/prescriptions/{id}/print` only ever returned
*layout* data — header/footer/margins — for a client-side renderer; no PDF
bytes were ever produced anywhere in this backend). `fpdf2` was chosen
over `weasyprint`/`xhtml2pdf` specifically because it's pure Python — no
system-level Cairo/Pango dependency to install on a Windows dev machine or
a container image, matching "keep it lean."

This module is a pure renderer — no DB access, no session. All data it
needs (patient/doctor names, resolved letterhead, item list) is resolved
by the caller (`PrescriptionService`) beforehand and passed in as plain
values, the same "business logic in service, rendering elsewhere"
separation `app/modules/notifications/service.py::render_body` and
`app/modules/letterhead/service.py` already keep.
"""

from dataclasses import dataclass
from datetime import datetime

from fpdf import FPDF

from app.modules.letterhead.schemas import LetterheadResolved


@dataclass(frozen=True)
class PrescriptionPdfItem:
    medicine_name: str
    dosage: str | None
    frequency: str | None
    duration: str | None
    route: str | None
    prescribed_quantity: int
    instructions: str | None


def render_prescription_pdf(
    *, patient_name: str, doctor_name: str, issued_at: datetime, items: list[PrescriptionPdfItem], letterhead: LetterheadResolved,
) -> bytes:
    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    if letterhead.header is not None:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, letterhead.header.clinic_name or "", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        if letterhead.header.branch_name:
            pdf.cell(0, 5, letterhead.header.branch_name, new_x="LMARGIN", new_y="NEXT")
        if letterhead.header.address:
            pdf.cell(0, 5, letterhead.header.address, new_x="LMARGIN", new_y="NEXT")
        if letterhead.header.contact:
            pdf.cell(0, 5, letterhead.header.contact, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Prescription", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Patient: {patient_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Doctor: {doctor_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Issued: {issued_at.strftime('%d %b %Y, %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    col_widths = (55, 30, 30, 25, 20, 30)
    headers = ("Medicine", "Dosage", "Frequency", "Duration", "Route", "Qty")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(235, 235, 235)
    for width, header in zip(col_widths, headers):
        pdf.cell(width, 7, header, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for item in items:
        row = (
            item.medicine_name, item.dosage or "-", item.frequency or "-", item.duration or "-",
            item.route or "-", str(item.prescribed_quantity),
        )
        for width, value in zip(col_widths, row):
            pdf.cell(width, 7, value, border=1)
        pdf.ln()
        if item.instructions:
            pdf.set_font("Helvetica", "I", 8)
            pdf.multi_cell(0, 5, f"  Instructions: {item.instructions}")
            pdf.set_font("Helvetica", "", 9)

    if letterhead.footer is not None:
        pdf.set_y(-30)
        pdf.set_draw_color(180, 180, 180)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.set_font("Helvetica", "I", 8)
        pdf.ln(2)
        footer_text = " | ".join(v for v in (letterhead.footer.clinic_name, letterhead.footer.address, letterhead.footer.contact) if v)
        if footer_text:
            pdf.cell(0, 5, footer_text, new_x="LMARGIN", new_y="NEXT", align="C")

    output = pdf.output()
    return bytes(output)
