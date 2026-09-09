import { Plus, Receipt } from 'lucide-react'
import { useState } from 'react'
import { ExpenseFormDialog } from '@/components/expenses/expense-form-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useBranches } from '@/features/branches/hooks'
import { useExpenseSearch } from '@/features/expenses/hooks'
import { EXPENSE_CATEGORIES, type ExpenseCategory, type ExpenseSummary } from '@/features/expenses/types'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function ExpensesPage() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('expenses.manage')
  const canRecord = hasPermission('expenses.record')
  const { data: branches } = useBranches()

  const [branchId, setBranchId] = useState('')
  const [category, setCategory] = useState<ExpenseCategory | ''>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [formExpense, setFormExpense] = useState<ExpenseSummary | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const { data, isLoading } = useExpenseSearch({
    branchId: branchId || undefined,
    category: category || undefined,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    limit: 50,
  })
  const expenses = data?.items ?? []
  const columnCount = 6 + (canManage ? 1 : 0)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Expenses</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Clinic operating expenses.</p>
        </div>
        {(canManage || canRecord) && (
          <Button
            className="gap-1.5"
            onClick={() => {
              setFormExpense(null)
              setFormOpen(true)
            }}
          >
            <Plus className="size-4" />
            Record expense
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-end gap-3">
        {branches && branches.length > 1 && (
          <Select value={branchId || 'ALL'} onValueChange={(value) => setBranchId(value === 'ALL' ? '' : (value ?? ''))}>
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue placeholder="All branches" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All branches</SelectItem>
              {branches.map((branch) => (
                <SelectItem key={branch.id} value={branch.id}>
                  {branch.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select value={category || 'ALL'} onValueChange={(value) => setCategory(value === 'ALL' ? '' : ((value ?? '') as ExpenseCategory))}>
          <SelectTrigger className="w-full sm:w-44">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All categories</SelectItem>
            {EXPENSE_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="expenseDateFrom" className="text-xs font-medium text-slate-500 dark:text-slate-400">
            From
          </label>
          <input
            id="expenseDateFrom"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm dark:border-slate-800 dark:bg-slate-950"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="expenseDateTo" className="text-xs font-medium text-slate-500 dark:text-slate-400">
            To
          </label>
          <input
            id="expenseDateTo"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm dark:border-slate-800 dark:bg-slate-950"
          />
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Vendor</TableHead>
              <TableHead>Payment mode</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Recorded by</TableHead>
              {canManage && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: columnCount }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && expenses.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columnCount}>
                  <EmptyState
                    icon={Receipt}
                    title="No expenses found"
                    description={canManage || canRecord ? 'Record an expense to get started.' : 'No expenses match these filters.'}
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              expenses.map((expense) => (
                <TableRow key={expense.id}>
                  <TableCell className="text-slate-600 dark:text-slate-400">{new Date(expense.expense_date).toLocaleDateString()}</TableCell>
                  <TableCell className="text-slate-700 dark:text-slate-300">{expense.category}</TableCell>
                  <TableCell className="text-slate-700 dark:text-slate-300">{expense.vendor || '—'}</TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{expense.payment_mode}</TableCell>
                  <TableCell className="text-right font-medium text-slate-900 dark:text-slate-100">{formatMoney(expense.amount)}</TableCell>
                  <TableCell className="text-xs text-slate-400 dark:text-slate-500">{expense.recorded_by.slice(0, 8)}</TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setFormExpense(expense)
                          setFormOpen(true)
                        }}
                      >
                        Edit
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
          {!isLoading && expenses.length > 0 && data && (
            <TableFooter>
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={4} className="text-right font-medium text-slate-500 dark:text-slate-400">
                  Total ({data.total} expense{data.total === 1 ? '' : 's'})
                </TableCell>
                <TableCell className="text-right font-semibold text-slate-900 dark:text-slate-100">{formatMoney(data.total_amount)}</TableCell>
                <TableCell colSpan={canManage ? 2 : 1} />
              </TableRow>
            </TableFooter>
          )}
        </Table>
      </div>

      <ExpenseFormDialog expense={formExpense} open={formOpen} onOpenChange={setFormOpen} />
    </div>
  )
}
