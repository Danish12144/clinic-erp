import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useCreateMedicine, useUpdateMedicine } from '@/features/pharmacy/hooks'
import type { MedicineSummary } from '@/features/pharmacy/types'
import { getErrorMessage } from '@/lib/errors'

const medicineFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(300),
  genericName: z.string().max(300).optional().or(z.literal('')),
  category: z.string().max(200).optional().or(z.literal('')),
  dosageForm: z.string().max(100).optional().or(z.literal('')),
  strength: z.string().max(100).optional().or(z.literal('')),
  manufacturer: z.string().max(300).optional().or(z.literal('')),
  unitPrice: z.string().refine((v) => !v || Number(v) >= 0, 'Must be 0 or more'),
  sku: z.string().max(100).optional().or(z.literal('')),
  reorderThreshold: z.string().refine((v) => !v || Number.isInteger(Number(v)) && Number(v) >= 0, 'Must be a whole number'),
})

type MedicineFormValues = z.infer<typeof medicineFormSchema>

function toFormValues(medicine: MedicineSummary | null): MedicineFormValues {
  return {
    name: medicine?.name ?? '',
    genericName: medicine?.generic_name ?? '',
    category: medicine?.category ?? '',
    dosageForm: medicine?.dosage_form ?? '',
    strength: medicine?.strength ?? '',
    manufacturer: medicine?.manufacturer ?? '',
    unitPrice: medicine?.unit_price ?? '0',
    sku: medicine?.sku ?? '',
    reorderThreshold: medicine ? String(medicine.reorder_threshold) : '0',
  }
}

export function MedicineFormDialog({
  medicine,
  open,
  onOpenChange,
}: {
  medicine: MedicineSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createMedicine = useCreateMedicine()
  const updateMedicine = useUpdateMedicine()
  const isEditing = Boolean(medicine)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MedicineFormValues>({ resolver: zodResolver(medicineFormSchema), defaultValues: toFormValues(medicine) })

  useEffect(() => {
    if (open) reset(toFormValues(medicine))
  }, [open, medicine, reset])

  async function onSubmit(values: MedicineFormValues) {
    const payload = {
      name: values.name,
      generic_name: values.genericName || undefined,
      category: values.category || undefined,
      dosage_form: values.dosageForm || undefined,
      strength: values.strength || undefined,
      manufacturer: values.manufacturer || undefined,
      unit_price: values.unitPrice || undefined,
      sku: values.sku || undefined,
      reorder_threshold: values.reorderThreshold ? Number(values.reorderThreshold) : undefined,
    }
    try {
      if (medicine) {
        await updateMedicine.mutateAsync({ medicineId: medicine.id, payload })
        toast.success('Medicine updated')
      } else {
        await createMedicine.mutateAsync(payload)
        toast.success('Medicine added to catalog')
      }
      onOpenChange(false)
    } catch (error) {
      toast.error(`Could not ${isEditing ? 'update' : 'create'} medicine`, { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit medicine' : 'Add medicine'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" {...register('name')} />
              {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="genericName">Generic name</Label>
              <Input id="genericName" {...register('genericName')} />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category">Category</Label>
              <Input id="category" {...register('category')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="dosageForm">Dosage form</Label>
              <Input id="dosageForm" placeholder="Tablet" {...register('dosageForm')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="strength">Strength</Label>
              <Input id="strength" placeholder="500mg" {...register('strength')} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="manufacturer">Manufacturer</Label>
            <Input id="manufacturer" {...register('manufacturer')} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="unitPrice">Unit price</Label>
              <Input id="unitPrice" type="number" min={0} step="0.01" {...register('unitPrice')} />
              {errors.unitPrice && <p className="text-sm text-destructive">{errors.unitPrice.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sku">SKU</Label>
              <Input id="sku" {...register('sku')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reorderThreshold">Reorder at</Label>
              <Input id="reorderThreshold" type="number" min={0} step="1" {...register('reorderThreshold')} />
              {errors.reorderThreshold && <p className="text-sm text-destructive">{errors.reorderThreshold.message}</p>}
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : isEditing ? 'Save changes' : 'Add medicine'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
