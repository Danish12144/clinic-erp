"""Patient EMR Timeline & Medical Documents — PRD-ARCHITECTURE.md §4
(module list item 16), §6, §15, migration 0016.

`MedicalDocument` is the only new table this module owns — the timeline
endpoint is pure read-aggregation over other modules' tables (`encounters`,
`consultations`, `prescriptions`/`prescription_items`, `vitals`, and this
module's own `medical_documents`), the same "no new tables for the read
side" shape Financial Reports used. See this migration's docstring for why
`medical_documents` is a purpose-built, directly-FK'd table rather than a
reuse of the master schema's still-unbuilt polymorphic `documents`.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, ForeignKey, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MedicalDocumentType(str, PyEnum):
    LAB_REPORT = "LAB_REPORT"
    SCAN = "SCAN"
    XRAY = "XRAY"
    OTHER = "OTHER"


medical_document_type_enum = SAEnum(
    MedicalDocumentType, name="medical_document_type", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class MedicalDocument(Base):
    __tablename__ = "medical_documents"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id"), nullable=True)
    document_type: Mapped[MedicalDocumentType] = mapped_column(medical_document_type_enum, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
