import { describe, expect, it } from 'vitest'
import { expenseFormSchema } from '@/components/expenses/expense-form-dialog'

const VALID = {
  branchId: 'branch-1',
  category: 'RENT' as const,
  amount: '1500.00',
  expenseDate: '2026-09-11',
  paymentMode: 'CASH' as const,
  vendor: '',
  notes: '',
}

describe('expenseFormSchema', () => {
  it('accepts a fully valid expense', () => {
    expect(expenseFormSchema.safeParse(VALID).success).toBe(true)
  })

  it('rejects a missing branch', () => {
    const result = expenseFormSchema.safeParse({ ...VALID, branchId: '' })
    expect(result.success).toBe(false)
  })

  it('rejects a zero or negative amount', () => {
    expect(expenseFormSchema.safeParse({ ...VALID, amount: '0' }).success).toBe(false)
    expect(expenseFormSchema.safeParse({ ...VALID, amount: '-5' }).success).toBe(false)
  })

  it('rejects a non-numeric amount', () => {
    expect(expenseFormSchema.safeParse({ ...VALID, amount: 'not-a-number' }).success).toBe(false)
  })

  it('rejects a category outside EXPENSE_CATEGORIES', () => {
    expect(expenseFormSchema.safeParse({ ...VALID, category: 'BRIBERY' }).success).toBe(false)
  })

  it('rejects a missing expense date', () => {
    expect(expenseFormSchema.safeParse({ ...VALID, expenseDate: '' }).success).toBe(false)
  })
})
