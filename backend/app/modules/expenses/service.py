"""Clinic Expenses business logic — see app/modules/expenses/models.py's
module docstring and PRD-ARCHITECTURE.md §6.

No row-scoping anywhere in this module — unlike most other financial
modules this session, Doctor and every other non-Owner/Receptionist role
has *zero* access (task 3), so there's no "own records" tier to carve out;
Owner and Receptionist are both tenant-wide. `expenses.manage` (Owner)
gates create/read/update; `expenses.record` (Receptionist, a deliberate
matrix deviation — see migration 0020's docstring) gates create/read only.
"""

import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from app.core.db import tenant_session
from app.modules.audit.service import record as record_audit
from app.modules.expenses.models import ExpenseCategory, ExpensePaymentMode
from app.modules.expenses.repository import ExpenseRepository
from app.modules.expenses.schemas import (
    ExpenseCreateRequest,
    ExpenseListResponse,
    ExpenseSummary,
    ExpenseUpdateRequest,
)
from app.modules.tenancy.repository import BranchRepository, ClinicRepository


async def _clinic_local_today(session, tenant_id: uuid.UUID) -> date:
    """`Expense.expense_date`'s DB `server_default=func.current_date()`
    evaluates in Postgres's own session timezone (UTC, unconditionally —
    confirmed via `SHOW timezone`), not the clinic's configured
    `Clinic.timezone` (default `'Asia/Kolkata'`, validated as a real IANA
    zone at write time by `app/modules/tenancy/schemas.py`, so `ZoneInfo`
    here never raises). For a UTC+5:30 clinic, "today" by the DB's UTC
    default and "today" on the clinic's own wall calendar disagree for
    ~5.5 hours out of every day (00:00-05:29 IST) — not a rare edge case.
    This computes the real thing "defaults to today" was always supposed
    to mean, so the app now always sets `expense_date` explicitly instead
    of leaning on the DB default."""
    clinic = await ClinicRepository(session).get_by_id(tenant_id)
    tz = ZoneInfo(clinic.timezone) if clinic is not None else timezone.utc
    return datetime.now(tz).date()


class ExpenseService:
    async def create_expense(self, *, tenant_id: uuid.UUID, payload: ExpenseCreateRequest, actor_user_id: uuid.UUID, actor_role: str) -> ExpenseSummary:
        async with tenant_session(tenant_id) as session:
            if await BranchRepository(session).get_by_id(payload.branch_id) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{payload.branch_id}' does not exist")

            fields = payload.model_dump(exclude={"expense_date"})
            fields["expense_date"] = payload.expense_date or await _clinic_local_today(session, tenant_id)

            expense = await ExpenseRepository(session).create(tenant_id=tenant_id, recorded_by=actor_user_id, **fields)
            summary = ExpenseSummary.model_validate(expense)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="expense.create", entity_type="expense", entity_id=expense.id, before=None, after=summary.model_dump(mode="json"),
            )
            return summary

    async def update_expense(self, *, tenant_id: uuid.UUID, expense_id: uuid.UUID, payload: ExpenseUpdateRequest, actor_user_id: uuid.UUID, actor_role: str) -> ExpenseSummary:
        async with tenant_session(tenant_id) as session:
            repo = ExpenseRepository(session)
            expense = await repo.get_by_id(expense_id)
            if expense is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")

            changes = payload.model_dump(exclude_unset=True)
            if "branch_id" in changes and await BranchRepository(session).get_by_id(changes["branch_id"]) is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Branch '{changes['branch_id']}' does not exist")

            before = ExpenseSummary.model_validate(expense).model_dump(mode="json")
            await repo.update_fields(expense_id, **changes)
            updated = await repo.get_by_id(expense_id)
            assert updated is not None
            after = ExpenseSummary.model_validate(updated)
            await record_audit(
                session, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_role=actor_role,
                action="expense.update", entity_type="expense", entity_id=expense_id, before=before, after=after.model_dump(mode="json"),
            )
            return after

    async def get_expense(self, *, tenant_id: uuid.UUID, expense_id: uuid.UUID) -> ExpenseSummary:
        async with tenant_session(tenant_id) as session:
            expense = await ExpenseRepository(session).get_by_id(expense_id)
            if expense is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
            return ExpenseSummary.model_validate(expense)

    async def search_expenses(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, category: ExpenseCategory | None,
        payment_mode: ExpensePaymentMode | None, date_from: date | None, date_to: date | None, limit: int, offset: int,
    ) -> ExpenseListResponse:
        async with tenant_session(tenant_id) as session:
            rows, total, total_amount = await ExpenseRepository(session).search(
                tenant_id=tenant_id, branch_id=branch_id, category=category, payment_mode=payment_mode,
                date_from=date_from, date_to=date_to, limit=limit, offset=offset,
            )
            return ExpenseListResponse(items=[ExpenseSummary.model_validate(e) for e in rows], total=total, limit=limit, offset=offset, total_amount=total_amount)
