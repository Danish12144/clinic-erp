import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useBranches } from '@/features/branches/hooks'
import { useCreateExpense, useUpdateExpense } from '@/features/expenses/hooks'
import { EXPENSE_CATEGORIES, EXPENSE_PAYMENT_MODES, type ExpenseSummary } from '@/features/expenses/types'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput } from '@/lib/working-hours'

export const expenseFormSchema = z.object({
  branchId: z.string().min(1, 'Branch is required'),
  category: z.enum(EXPENSE_CATEGORIES),
  amount: z.string().refine((v) => Number(v) > 0, 'Amount must be greater than 0'),
  expenseDate: z.string().min(1, 'Date is required'),
  paymentMode: z.enum(EXPENSE_PAYMENT_MODES),
  vendor: z.string().max(300).optional().or(z.literal('')),
  notes: z.string().max(1000).optional().or(z.literal('')),
})

type ExpenseFormValues = z.infer<typeof expenseFormSchema>

function toFormValues(expense: ExpenseSummary | null, defaultBranchId: string): ExpenseFormValues {
  return {
    branchId: expense?.branch_id ?? defaultBranchId,
    category: (expense?.category as ExpenseFormValues['category']) ?? 'OTHER',
    amount: expense?.amount ?? '',
    expenseDate: expense ? expense.expense_date : formatDateInput(new Date()),
    paymentMode: (expense?.payment_mode as ExpenseFormValues['paymentMode']) ?? 'CASH',
    vendor: expense?.vendor ?? '',
    notes: expense?.notes ?? '',
  }
}

export function ExpenseFormDialog({
  expense,
  open,
  onOpenChange,
}: {
  expense: ExpenseSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: branches } = useBranches()
  const createExpense = useCreateExpense()
  const updateExpense = useUpdateExpense()
  const isEditing = Boolean(expense)

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ExpenseFormValues>({
    resolver: zodResolver(expenseFormSchema),
    defaultValues: toFormValues(expense, branches?.[0]?.id ?? ''),
  })

  useEffect(() => {
    if (open) reset(toFormValues(expense, branches?.[0]?.id ?? ''))
  }, [open, expense, branches, reset])

  async function onSubmit(values: ExpenseFormValues) {
    try {
      if (expense) {
        await updateExpense.mutateAsync({
          expenseId: expense.id,
          payload: {
            branch_id: values.branchId,
            category: values.category,
            amount: values.amount,
            expense_date: values.expenseDate,
            payment_mode: values.paymentMode,
            vendor: values.vendor || undefined,
            notes: values.notes || undefined,
          },
        })
        toast.success('Expense updated')
      } else {
        await createExpense.mutateAsync({
          branch_id: values.branchId,
          category: values.category,
          amount: values.amount,
          expense_date: values.expenseDate,
          payment_mode: values.paymentMode,
          vendor: values.vendor || undefined,
          notes: values.notes || undefined,
        })
        toast.success('Expense recorded')
      }
      onOpenChange(false)
    } catch (error) {
      toast.error(`Could not ${isEditing ? 'update' : 'record'} expense`, { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit expense' : 'Record expense'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          {branches && branches.length > 1 && (
            <div className="flex flex-col gap-1.5">
              <Label>Branch</Label>
              <Select value={watch('branchId')} onValueChange={(value) => value && setValue('branchId', value)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {branches.map((branch) => (
                    <SelectItem key={branch.id} value={branch.id}>
                      {branch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.branchId && <p className="text-sm text-destructive">{errors.branchId.message}</p>}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Category</Label>
              <Select value={watch('category')} onValueChange={(value) => value && setValue('category', value as ExpenseFormValues['category'])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXPENSE_CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Payment mode</Label>
              <Select value={watch('paymentMode')} onValueChange={(value) => value && setValue('paymentMode', value as ExpenseFormValues['paymentMode'])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {EXPENSE_PAYMENT_MODES.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="expenseAmount">Amount</Label>
              <Input id="expenseAmount" type="number" min={0.01} step="0.01" {...register('amount')} />
              {errors.amount && <p className="text-sm text-destructive">{errors.amount.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="expenseDate">Date</Label>
              <Input id="expenseDate" type="date" {...register('expenseDate')} />
              {errors.expenseDate && <p className="text-sm text-destructive">{errors.expenseDate.message}</p>}
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="expenseVendor">Vendor</Label>
            <Input id="expenseVendor" {...register('vendor')} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="expenseNotes">Notes</Label>
            <Textarea id="expenseNotes" rows={2} {...register('notes')} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : isEditing ? 'Save changes' : 'Record expense'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
