"""API surface for Clinic Expenses — PRD-ARCHITECTURE.md §8:
`/api/v1/expenses/*`.

`expenses.manage` (Owner, matches the PRD §3 matrix's "F" exactly) gates
create/read/update. `expenses.record` (Receptionist, a deliberate matrix
deviation — see migration 0020's docstring) gates create/read only, never
update. Doctor and every other role has neither permission at all —
"Doctor/Staff have zero access" (task 3).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, require_any_permission, require_permission
from app.modules.expenses.models import ExpenseCategory, ExpensePaymentMode
from app.modules.expenses.schemas import (
    ExpenseCreateRequest,
    ExpenseListResponse,
    ExpenseSummary,
    ExpenseUpdateRequest,
)
from app.modules.expenses.service import ExpenseService

router = APIRouter(prefix="/api/v1/expenses", tags=["expenses"])

_READ_WRITE_PERMS = ("expenses.manage", "expenses.record")


def get_expense_service() -> ExpenseService:
    return ExpenseService()


@router.post("", response_model=ExpenseSummary, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreateRequest,
    current_user: CurrentUser = Depends(require_any_permission(*_READ_WRITE_PERMS)),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseSummary:
    return await service.create_expense(tenant_id=current_user.tenant_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)


@router.get("", response_model=ExpenseListResponse)
async def search_expenses(
    branch_id: uuid.UUID | None = Query(None),
    category: ExpenseCategory | None = Query(None),
    payment_mode: ExpensePaymentMode | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_any_permission(*_READ_WRITE_PERMS)),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseListResponse:
    return await service.search_expenses(
        tenant_id=current_user.tenant_id, branch_id=branch_id, category=category, payment_mode=payment_mode,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )


@router.get("/{expense_id}", response_model=ExpenseSummary)
async def get_expense(
    expense_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_permission(*_READ_WRITE_PERMS)),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseSummary:
    return await service.get_expense(tenant_id=current_user.tenant_id, expense_id=expense_id)


@router.patch("/{expense_id}", response_model=ExpenseSummary)
async def update_expense(
    expense_id: uuid.UUID,
    payload: ExpenseUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("expenses.manage")),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseSummary:
    return await service.update_expense(tenant_id=current_user.tenant_id, expense_id=expense_id, payload=payload, actor_user_id=current_user.user_id, actor_role=current_user.role_code)
