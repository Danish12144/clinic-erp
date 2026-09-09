import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createExpense, searchExpenses, updateExpense } from '@/features/expenses/api'
import { useAuth } from '@/features/auth/auth-context'
import type { ExpenseCreateRequest, ExpenseSearchParams, ExpenseUpdateRequest } from '@/features/expenses/types'

const READ_WRITE_PERMS = ['expenses.manage', 'expenses.record']

export function useExpenseSearch(params: ExpenseSearchParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['expenses', 'search', params],
    queryFn: () => searchExpenses(params),
    enabled: READ_WRITE_PERMS.some(hasPermission),
    placeholderData: keepPreviousData,
  })
}

function useInvalidateExpenses() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['expenses'] })
}

export function useCreateExpense() {
  const invalidate = useInvalidateExpenses()
  return useMutation({
    mutationFn: (payload: ExpenseCreateRequest) => createExpense(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateExpense() {
  const invalidate = useInvalidateExpenses()
  return useMutation({
    mutationFn: ({ expenseId, payload }: { expenseId: string; payload: ExpenseUpdateRequest }) => updateExpense(expenseId, payload),
    onSuccess: invalidate,
  })
}
