import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.expenses.models import Expense, ExpenseCategory, ExpensePaymentMode


class ExpenseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, tenant_id: uuid.UUID, recorded_by: uuid.UUID, **fields: object) -> Expense:
        expense = Expense(tenant_id=tenant_id, recorded_by=recorded_by, **fields)
        self._session.add(expense)
        await self._session.flush()
        return expense

    async def get_by_id(self, expense_id: uuid.UUID) -> Expense | None:
        result = await self._session.execute(select(Expense).where(Expense.id == expense_id))
        return result.scalar_one_or_none()

    async def update_fields(self, expense_id: uuid.UUID, **fields: object) -> None:
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(update(Expense).where(Expense.id == expense_id).values(**fields))

    @staticmethod
    def _filters(
        *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, category: ExpenseCategory | None,
        payment_mode: ExpensePaymentMode | None, date_from: date | None, date_to: date | None,
    ) -> list:
        filters = [Expense.tenant_id == tenant_id]
        if branch_id:
            filters.append(Expense.branch_id == branch_id)
        if category:
            filters.append(Expense.category == category)
        if payment_mode:
            filters.append(Expense.payment_mode == payment_mode)
        if date_from:
            filters.append(Expense.expense_date >= date_from)
        if date_to:
            filters.append(Expense.expense_date <= date_to)
        return filters

    async def search(
        self, *, tenant_id: uuid.UUID, branch_id: uuid.UUID | None, category: ExpenseCategory | None,
        payment_mode: ExpensePaymentMode | None, date_from: date | None, date_to: date | None, limit: int, offset: int,
    ) -> tuple[list[Expense], int, Decimal]:
        filters = self._filters(tenant_id=tenant_id, branch_id=branch_id, category=category, payment_mode=payment_mode, date_from=date_from, date_to=date_to)

        count_result = await self._session.execute(select(func.count()).select_from(Expense).where(*filters))
        total = count_result.scalar_one()

        sum_result = await self._session.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(*filters))
        total_amount = Decimal(sum_result.scalar_one()).quantize(Decimal("0.01"))

        page_result = await self._session.execute(
            select(Expense).where(*filters).order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(limit).offset(offset)
        )
        return list(page_result.scalars().all()), total, total_amount
