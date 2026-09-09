import { apiClient } from '@/lib/api-client'
import type {
  ExpenseCreateRequest,
  ExpenseListResponse,
  ExpenseSearchParams,
  ExpenseSummary,
  ExpenseUpdateRequest,
} from '@/features/expenses/types'

export async function searchExpenses(params: ExpenseSearchParams): Promise<ExpenseListResponse> {
  const { data } = await apiClient.get<ExpenseListResponse>('/expenses', {
    params: {
      branch_id: params.branchId || undefined,
      category: params.category || undefined,
      payment_mode: params.paymentMode || undefined,
      date_from: params.dateFrom || undefined,
      date_to: params.dateTo || undefined,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getExpense(expenseId: string): Promise<ExpenseSummary> {
  const { data } = await apiClient.get<ExpenseSummary>(`/expenses/${expenseId}`)
  return data
}

export async function createExpense(payload: ExpenseCreateRequest): Promise<ExpenseSummary> {
  const { data } = await apiClient.post<ExpenseSummary>('/expenses', payload)
  return data
}

export async function updateExpense(expenseId: string, payload: ExpenseUpdateRequest): Promise<ExpenseSummary> {
  const { data } = await apiClient.patch<ExpenseSummary>(`/expenses/${expenseId}`, payload)
  return data
}
