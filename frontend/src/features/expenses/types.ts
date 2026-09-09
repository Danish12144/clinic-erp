// Mirrors backend/app/modules/expenses/schemas.py + models.py — keep in sync with those files.

export const EXPENSE_CATEGORIES = ['RENT', 'UTILITIES', 'SUPPLIES', 'SALARY', 'MAINTENANCE', 'MARKETING', 'OTHER'] as const
export type ExpenseCategory = (typeof EXPENSE_CATEGORIES)[number]

export const EXPENSE_PAYMENT_MODES = ['CASH', 'UPI', 'CARD', 'BANK_TRANSFER'] as const
export type ExpensePaymentMode = (typeof EXPENSE_PAYMENT_MODES)[number]

export interface ExpenseSummary {
  id: string
  tenant_id: string
  branch_id: string
  category: string
  amount: string
  expense_date: string
  payment_mode: string
  vendor: string | null
  notes: string | null
  receipt_document_id: string | null
  recorded_by: string
  created_at: string
  updated_at: string
}

export interface ExpenseListResponse {
  items: ExpenseSummary[]
  total: number
  limit: number
  offset: number
  total_amount: string
}

export interface ExpenseSearchParams {
  branchId?: string
  category?: ExpenseCategory
  paymentMode?: ExpensePaymentMode
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}

export interface ExpenseCreateRequest {
  branch_id: string
  category: ExpenseCategory
  amount: string
  expense_date?: string
  payment_mode: ExpensePaymentMode
  vendor?: string
  notes?: string
}

export interface ExpenseUpdateRequest {
  branch_id?: string
  category?: ExpenseCategory
  amount?: string
  expense_date?: string
  payment_mode?: ExpensePaymentMode
  vendor?: string
  notes?: string
}
