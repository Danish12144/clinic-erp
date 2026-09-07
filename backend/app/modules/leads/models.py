"""Lead Pipeline / CRM Funnel — PRD-ARCHITECTURE.md §4 (module list item
28), §20, §6, migration 0023. See that migration's docstring for the
deliberate deviations from the master schema's `leads` sketch (real
`source`/`status` enums, `status` being a wholly new `lead_status` rather
than the sketch's `lead_stage`, `first_name`/`last_name` over a single
`name`) and for why `lead_interactions` is a new table with no master
schema sketch at all.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import ForeignKey, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LeadSource(str, PyEnum):
    GOOGLE_AD = "GOOGLE_AD"
    WALK_IN = "WALK_IN"
    WEBSITE = "WEBSITE"
    REFERRAL = "REFERRAL"
    SOCIAL = "SOCIAL"


lead_source_enum = SAEnum(LeadSource, name="lead_source", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class LeadStatus(str, PyEnum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    APPOINTMENT_SCHEDULED = "APPOINTMENT_SCHEDULED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


lead_status_enum = SAEnum(LeadStatus, name="lead_status", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class LeadInteractionType(str, PyEnum):
    CALL = "CALL"
    WHATSAPP = "WHATSAPP"
    NOTE = "NOTE"
    EMAIL = "EMAIL"


lead_interaction_type_enum = SAEnum(
    LeadInteractionType, name="lead_interaction_type", create_type=False, values_callable=lambda enum: [m.value for m in enum]
)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[LeadSource | None] = mapped_column(lead_source_enum, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(lead_status_enum, nullable=False, server_default=text("'NEW'::lead_status"))
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    converted_patient_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeadInteraction(Base):
    """Insert-only outreach-activity log — no update method exists in this
    module's repository, same convention as `payments`/
    `pharmacy_inventory_transactions`/`communication_logs`."""

    __tablename__ = "lead_interactions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    interaction_type: Mapped[LeadInteractionType] = mapped_column(lead_interaction_type_enum, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
