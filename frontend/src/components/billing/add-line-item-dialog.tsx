import { zodResolver } from '@hookform/resolvers/zod'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAddLineItem } from '@/features/billing/hooks'
import { INVOICE_LINE_SOURCES } from '@/features/billing/types'
import { getErrorMessage } from '@/lib/errors'

const SOURCE_LABELS: Record<string, string> = {
  CONSULTATION: 'Consultation',
  PROCEDURE: 'Procedure',
  PHARMACY: 'Pharmacy',
  LAB: 'Lab',
  OTHER: 'Other',
}

const lineItemSchema = z.object({
  sourceType: z.enum(INVOICE_LINE_SOURCES),
  description: z.string().min(1, 'Description is required').max(500),
  quantity: z.string().refine((v) => Number(v) > 0, 'Must be greater than 0'),
  unitPrice: z.string().refine((v) => Number(v) >= 0, 'Must be 0 or more'),
})

type LineItemFormValues = z.infer<typeof lineItemSchema>

export function AddLineItemDialog({
  invoiceId,
  open,
  onOpenChange,
}: {
  invoiceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const addLineItem = useAddLineItem(invoiceId)

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<LineItemFormValues>({
    resolver: zodResolver(lineItemSchema),
    defaultValues: { sourceType: 'OTHER', description: '', quantity: '1', unitPrice: '' },
  })

  async function onSubmit(values: LineItemFormValues) {
    try {
      await addLineItem.mutateAsync({
        source_type: values.sourceType,
        description: values.description,
        quantity: values.quantity,
        unit_price: values.unitPrice,
      })
      toast.success('Line item added')
      reset()
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not add line item', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add line item</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Type</Label>
            <Controller
              control={control}
              name="sourceType"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {INVOICE_LINE_SOURCES.map((source) => (
                      <SelectItem key={source} value={source}>
                        {SOURCE_LABELS[source]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="description">Description</Label>
            <Input id="description" {...register('description')} />
            {errors.description && <p className="text-sm text-destructive">{errors.description.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="quantity">Quantity</Label>
              <Input id="quantity" type="number" min={0.01} step="0.01" {...register('quantity')} />
              {errors.quantity && <p className="text-sm text-destructive">{errors.quantity.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="unitPrice">Unit price</Label>
              <Input id="unitPrice" type="number" min={0} step="0.01" {...register('unitPrice')} />
              {errors.unitPrice && <p className="text-sm text-destructive">{errors.unitPrice.message}</p>}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Adding…' : 'Add item'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
