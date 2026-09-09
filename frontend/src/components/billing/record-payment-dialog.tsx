import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useRecordPayment } from '@/features/billing/hooks'
import { PAYMENT_METHODS } from '@/features/billing/types'
import { getErrorMessage } from '@/lib/errors'

const METHOD_LABELS: Record<string, string> = {
  CASH: 'Cash',
  CARD: 'Card',
  UPI: 'UPI',
  NET_BANKING: 'Net banking',
  INSURANCE: 'Insurance',
  OTHER: 'Other',
}

const paymentSchema = z.object({
  amount: z.string().refine((v) => Number(v) > 0, 'Enter an amount greater than 0'),
  method: z.enum(PAYMENT_METHODS),
  isRefund: z.boolean(),
  gatewayReference: z.string().max(300).optional().or(z.literal('')),
  notes: z.string().max(500).optional().or(z.literal('')),
})

type PaymentFormValues = z.infer<typeof paymentSchema>

export function RecordPaymentDialog({
  invoiceId,
  balanceDue,
  open,
  onOpenChange,
}: {
  invoiceId: string
  balanceDue: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const recordPayment = useRecordPayment(invoiceId)

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<PaymentFormValues>({
    resolver: zodResolver(paymentSchema),
    defaultValues: { amount: balanceDue !== '0.00' ? balanceDue : '', method: 'CASH', isRefund: false, gatewayReference: '', notes: '' },
  })

  const isRefund = watch('isRefund')

  useEffect(() => {
    if (open) reset({ amount: balanceDue !== '0.00' ? balanceDue : '', method: 'CASH', isRefund: false, gatewayReference: '', notes: '' })
  }, [open, balanceDue, reset])

  async function onSubmit(values: PaymentFormValues) {
    try {
      const amount = Math.abs(Number(values.amount))
      await recordPayment.mutateAsync({
        invoice_id: invoiceId,
        amount: values.isRefund ? String(-amount) : String(amount),
        method: values.method,
        gateway_reference: values.gatewayReference || undefined,
        notes: values.notes || undefined,
      })
      toast.success(values.isRefund ? 'Refund recorded' : 'Payment recorded')
      reset()
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not record payment', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Record payment</DialogTitle>
          <DialogDescription>Balance due: ₹{balanceDue}</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="amount">Amount</Label>
            <Input id="amount" type="number" min={0.01} step="0.01" {...register('amount')} />
            {errors.amount && <p className="text-sm text-destructive">{errors.amount.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label>Method</Label>
            <Controller
              control={control}
              name="method"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAYMENT_METHODS.map((method) => (
                      <SelectItem key={method} value={method}>
                        {METHOD_LABELS[method]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="gatewayReference">Reference (optional)</Label>
            <Input id="gatewayReference" placeholder="Transaction / receipt no." {...register('gatewayReference')} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Input id="notes" {...register('notes')} />
          </div>
          <div className="flex items-center gap-2">
            <Controller
              control={control}
              name="isRefund"
              render={({ field }) => <Checkbox id="isRefund" checked={field.value} onCheckedChange={field.onChange} />}
            />
            <Label htmlFor="isRefund" className="font-normal">
              This is a refund
            </Label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} variant={isRefund ? 'destructive' : 'default'}>
              {isSubmitting ? 'Saving…' : isRefund ? 'Record refund' : 'Record payment'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
