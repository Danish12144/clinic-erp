import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { createInvoice, issueInvoice, recordPayment } from '@/features/billing/api'
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

const feeSchema = z.object({
  description: z.string().min(1, 'Enter a description').max(500),
  amount: z.string().refine((v) => Number(v) > 0, 'Enter an amount greater than 0'),
  method: z.enum(PAYMENT_METHODS),
  markPaid: z.boolean(),
})

type FeeFormValues = z.infer<typeof feeSchema>

// The front-desk "pay first, see the doctor after" workflow: a Receptionist
// collecting vitals from a waiting patient can raise (and optionally
// settle) the consultation-fee invoice right there, without waiting for
// the doctor to complete the visit. This is exactly the scenario
// ConsultationService.complete_consultation's own auto-generate-on-
// completion comment already anticipates ("an invoice a receptionist
// already raised mid-visit... [is a] legitimate reason auto_generate_
// invoice 422s/409s... neither should block the consultation from
// completing") — no backend change needed, this dialog is simply the
// first real caller of that already-designed path. Three sequential API
// calls, not one hook-per-mutation, since the invoice id from step 1 is
// needed by steps 2/3: create (DRAFT, one CONSULTATION line item) ->
// issue (DRAFT -> ISSUED, required before a payment can be recorded) ->
// optionally record the full payment (ISSUED -> PAID).
export function CollectConsultationFeeDialog({
  encounterId,
  patientId,
  branchId,
  defaultAmount,
  patientName,
  open,
  onOpenChange,
}: {
  encounterId: string
  patientId: string
  branchId: string
  defaultAmount: string | null
  patientName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FeeFormValues>({
    resolver: zodResolver(feeSchema),
    defaultValues: { description: 'Consultation Fee', amount: defaultAmount ?? '', method: 'CASH', markPaid: true },
  })

  useEffect(() => {
    if (open) reset({ description: 'Consultation Fee', amount: defaultAmount ?? '', method: 'CASH', markPaid: true })
  }, [open, defaultAmount, reset])

  async function onSubmit(values: FeeFormValues) {
    try {
      const invoice = await createInvoice({
        branch_id: branchId,
        patient_id: patientId,
        encounter_id: encounterId,
        source_type: 'CONSULTATION',
        line_items: [{ source_type: 'CONSULTATION', description: values.description, quantity: '1', unit_price: values.amount }],
      })
      const issued = await issueInvoice(invoice.id)
      if (values.markPaid) {
        await recordPayment({ invoice_id: invoice.id, amount: issued.total, method: values.method })
      }
      void queryClient.invalidateQueries({ queryKey: ['billing', 'invoices'] })
      toast.success(values.markPaid ? `Invoice created and marked PAID for ${patientName}` : `Invoice created for ${patientName}`)
      onOpenChange(false)
      navigate(`/billing/${invoice.id}`)
    } catch (error) {
      toast.error('Could not create invoice', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Collect consultation fee</DialogTitle>
          <DialogDescription>For {patientName} — creates and issues an invoice for this visit.</DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="feeDescription">Description</Label>
            <Input id="feeDescription" {...register('description')} />
            {errors.description && <p className="text-sm text-destructive">{errors.description.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="feeAmount">Amount</Label>
            <Input id="feeAmount" type="number" min={0.01} step="0.01" {...register('amount')} />
            {errors.amount && <p className="text-sm text-destructive">{errors.amount.message}</p>}
          </div>

          <div className="flex items-center gap-2">
            <Controller
              control={control}
              name="markPaid"
              render={({ field }) => <Checkbox id="markPaid" checked={field.value} onCheckedChange={field.onChange} />}
            />
            <Label htmlFor="markPaid" className="font-normal">
              Collected now — mark as paid
            </Label>
          </div>

          <Controller
            control={control}
            name="markPaid"
            render={({ field: markPaidField }) =>
              markPaidField.value ? (
                <div className="flex flex-col gap-1.5">
                  <Label>Payment method</Label>
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
              ) : (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  The invoice will be issued unpaid — collect payment later from the Billing page.
                </p>
              )
            }
          />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Create invoice'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
