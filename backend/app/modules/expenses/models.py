"""Clinic Expenses — PRD-ARCHITECTURE.md §4 (module list item 23), §6,
migration 0020. See that migration's docstring for the deliberate
deviations (`category`/`payment_mode` as real enums, `receipt_document_id`
with no FK yet, Receptionist's `expenses.record` matrix deviation).
"""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, ForeignKey, Numeric, Text, DateTime, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExpenseCategory(str, PyEnum):
    RENT = "RENT"
    UTILITIES = "UTILITIES"
    SUPPLIES = "SUPPLIES"
    SALARY = "SALARY"
    MAINTENANCE = "MAINTENANCE"
    MARKETING = "MARKETING"
    OTHER = "OTHER"


expense_category_enum = SAEnum(ExpenseCategory, name="expense_category", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class ExpensePaymentMode(str, PyEnum):
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"
    BANK_TRANSFER = "BANK_TRANSFER"


expense_payment_mode_enum = SAEnum(ExpensePaymentMode, name="expense_payment_mode", create_type=False, values_callable=lambda enum: [m.value for m in enum])


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(expense_category_enum, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    # server_default is UTC "today" (Postgres's own session timezone) and
    # is only a last-resort DB-level fallback — ExpenseService.create_expense
    # always sets this explicitly to the clinic's local today (via
    # Clinic.timezone) when the caller omits it, since the two disagree
    # for ~5.5 hours a day for a UTC+5:30 clinic.
    expense_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    payment_mode: Mapped[ExpensePaymentMode] = mapped_column(expense_payment_mode_enum, nullable=False)
    vendor: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_document_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
