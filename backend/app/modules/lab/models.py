"""Pathology / Diagnostic Lab Management — PRD-ARCHITECTURE.md §4 (module
list items 26/27), §5.5, §19, migration 0018. See that migration's
docstring for the deliberate schema deviations (`RESULTED` replacing
`PROCESSING`, `test_code`/`specimen_type`/`turnaround_hours` on the
catalog, the array-shaped `reference_ranges`, `patient_id`/`doctor_id` on
orders).
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class LabOrderStatus(str, PyEnum):
    ORDERED = "ORDERED"
    SAMPLE_COLLECTED = "SAMPLE_COLLECTED"
    RESULTED = "RESULTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


lab_order_status_enum = SAEnum(LabOrderStatus, name="lab_order_status", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class LabResultFlag(str, PyEnum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


lab_result_flag_enum = SAEnum(LabResultFlag, name="lab_result_flag", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class LabTestCatalogItem(Base):
    __tablename__ = "lab_test_catalog"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    test_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    specimen_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    turnaround_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    reference_ranges: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabOrder(Base):
    __tablename__ = "lab_orders"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    test_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("lab_test_catalog.id"), nullable=False)
    ordered_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[LabOrderStatus] = mapped_column(lab_order_status_enum, nullable=False, server_default=text("'ORDERED'::lab_order_status"))
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sample_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    test: Mapped["LabTestCatalogItem"] = relationship()
    results: Mapped[list["LabResult"]] = relationship(order_by="LabResult.created_at")


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    lab_order_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("lab_orders.id", ondelete="CASCADE"), nullable=False)
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    flag: Mapped[LabResultFlag] = mapped_column(lab_result_flag_enum, nullable=False, server_default=text("'NORMAL'::lab_result_flag"))
    entered_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
