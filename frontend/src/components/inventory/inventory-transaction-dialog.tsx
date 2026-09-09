import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/features/auth/auth-context'
import { useRecordInventoryTransaction } from '@/features/inventory/hooks'
import { INVENTORY_CHANGE_TYPES, type InventoryChangeType, type InventoryItemSummary } from '@/features/inventory/types'
import { getErrorMessage } from '@/lib/errors'

const transactionSchema = z.object({
  changeType: z.enum(INVENTORY_CHANGE_TYPES),
  quantity: z.string().refine((v) => Number(v) !== 0, 'Quantity must not be zero'),
  notes: z.string().max(1000).optional().or(z.literal('')),
})

type TransactionFormValues = z.infer<typeof transactionSchema>

// inventory.record_usage callers (Receptionist/Nurse/Other Staff) may only
// ever submit change_type=USAGE — the backend 403s anything else for a
// non-Owner actor (InventoryService.record_transaction). Owner sees every
// change type.
export function InventoryTransactionDialog({
  item,
  open,
  onOpenChange,
}: {
  item: InventoryItemSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('inventory.manage')
  const availableChangeTypes = useMemo<InventoryChangeType[]>(
    () => (canManage ? [...INVENTORY_CHANGE_TYPES] : ['USAGE']),
    [canManage],
  )

  const recordTransaction = useRecordInventoryTransaction()

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<TransactionFormValues>({
    resolver: zodResolver(transactionSchema),
    defaultValues: { changeType: availableChangeTypes[0], quantity: '', notes: '' },
  })

  useEffect(() => {
    if (open) reset({ changeType: availableChangeTypes[0], quantity: '', notes: '' })
  }, [open, availableChangeTypes, reset])

  const changeType = watch('changeType')
  const allowsNegative = changeType === 'ADJUSTMENT'

  async function onSubmit(values: TransactionFormValues) {
    if (!item) return
    try {
      await recordTransaction.mutateAsync({
        itemId: item.id,
        payload: { change_type: values.changeType, quantity: values.quantity, notes: values.notes || undefined },
      })
      toast.success('Transaction recorded')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not record transaction', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Log transaction — {item?.name}</DialogTitle>
          <DialogDescription>Current stock: {item?.current_stock ?? '—'}</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Type</Label>
            <Select value={changeType} onValueChange={(value) => value && setValue('changeType', value as InventoryChangeType)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableChangeTypes.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txQuantity">Quantity {allowsNegative ? '(+/-)' : ''}</Label>
            <Input id="txQuantity" type="number" step="0.01" min={allowsNegative ? undefined : 0} {...register('quantity')} />
            {errors.quantity && <p className="text-sm text-destructive">{errors.quantity.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="txNotes">Notes</Label>
            <Textarea id="txNotes" rows={2} {...register('notes')} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Record transaction'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
