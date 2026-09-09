import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { useMedicineBatches, useReceiveStock } from '@/features/pharmacy/hooks'
import type { MedicineSummary } from '@/features/pharmacy/types'
import { getErrorMessage } from '@/lib/errors'

const batchSchema = z.object({
  batchNumber: z.string().min(1, 'Batch number is required').max(200),
  expiryDate: z.string().min(1, 'Expiry date is required'),
  quantity: z.string().refine((v) => Number.isInteger(Number(v)) && Number(v) >= 1, 'Must be a whole number, at least 1'),
  costPrice: z.string().optional().or(z.literal('')),
})

type BatchFormValues = z.infer<typeof batchSchema>

function isExpiringSoon(expiryDate: string): boolean {
  const days = (new Date(expiryDate).getTime() - Date.now()) / (24 * 60 * 60 * 1000)
  return days < 90
}

export function ReceiveStockDialog({
  medicine,
  open,
  onOpenChange,
}: {
  medicine: MedicineSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: batches, isLoading: batchesLoading } = useMedicineBatches(medicine?.id)
  const receiveStock = useReceiveStock()

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<BatchFormValues>({
    resolver: zodResolver(batchSchema),
    defaultValues: { batchNumber: '', expiryDate: '', quantity: '', costPrice: '' },
  })

  async function onSubmit(values: BatchFormValues) {
    if (!medicine) return
    try {
      await receiveStock.mutateAsync({
        medicineId: medicine.id,
        payload: {
          batch_number: values.batchNumber,
          expiry_date: values.expiryDate,
          quantity: Number(values.quantity),
          cost_price: values.costPrice || undefined,
        },
      })
      toast.success('Stock received')
      reset()
    } catch (error) {
      toast.error('Could not receive stock', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Receive stock — {medicine?.name}</DialogTitle>
          <DialogDescription>Add a new batch. Dispensing draws from the earliest-expiring batch first.</DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="batchNumber">Batch number</Label>
              <Input id="batchNumber" {...register('batchNumber')} />
              {errors.batchNumber && <p className="text-sm text-destructive">{errors.batchNumber.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="expiryDate">Expiry date</Label>
              <Input id="expiryDate" type="date" {...register('expiryDate')} />
              {errors.expiryDate && <p className="text-sm text-destructive">{errors.expiryDate.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quantity">Quantity</Label>
              <Input id="quantity" type="number" min={1} step="1" {...register('quantity')} />
              {errors.quantity && <p className="text-sm text-destructive">{errors.quantity.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="costPrice">Cost price (optional)</Label>
              <Input id="costPrice" type="number" min={0} step="0.01" {...register('costPrice')} />
            </div>
          </div>
          <Button type="submit" disabled={isSubmitting} className="w-fit">
            {isSubmitting ? 'Receiving…' : 'Receive stock'}
          </Button>
        </form>

        <Separator />

        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Existing batches</p>
          {batchesLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : !batches || batches.items.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No batches yet.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
              {batches.items.map((batch) => (
                <li key={batch.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{batch.batch_number}</span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      Expires {new Date(batch.expiry_date).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {isExpiringSoon(batch.expiry_date) && (
                      <Badge variant="outline" className="border-amber-300 text-amber-700 dark:text-amber-400">
                        Expiring soon
                      </Badge>
                    )}
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{batch.quantity_on_hand} on hand</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
