import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect } from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useCreateLabTest, useUpdateLabTest } from '@/features/lab/hooks'
import type { LabTestSummary } from '@/features/lab/types'
import { getErrorMessage } from '@/lib/errors'

const rangeRowSchema = z.object({
  min: z.string().optional().or(z.literal('')),
  max: z.string().optional().or(z.literal('')),
  unit: z.string().max(50).optional().or(z.literal('')),
  sex: z.enum(['', 'Male', 'Female', 'Other']).optional(),
  ageMin: z.string().optional().or(z.literal('')),
  ageMax: z.string().optional().or(z.literal('')),
})

const testFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(300),
  testCode: z.string().max(100).optional().or(z.literal('')),
  category: z.string().max(200).optional().or(z.literal('')),
  specimenType: z.string().max(200).optional().or(z.literal('')),
  turnaroundHours: z.string().optional().or(z.literal('')),
  price: z.string().refine((v) => !v || Number(v) >= 0, 'Must be 0 or more'),
  ranges: z.array(rangeRowSchema),
})

type TestFormValues = z.infer<typeof testFormSchema>

const EMPTY_RANGE_ROW = { min: '', max: '', unit: '', sex: '' as const, ageMin: '', ageMax: '' }

function toFormValues(test: LabTestSummary | null): TestFormValues {
  return {
    name: test?.name ?? '',
    testCode: test?.test_code ?? '',
    category: test?.category ?? '',
    specimenType: test?.specimen_type ?? '',
    turnaroundHours: test?.turnaround_hours != null ? String(test.turnaround_hours) : '',
    price: test?.price ?? '0',
    ranges:
      test?.reference_ranges.map((r) => ({
        min: r.min != null ? String(r.min) : '',
        max: r.max != null ? String(r.max) : '',
        unit: r.unit ?? '',
        sex: (r.sex ?? '') as '' | 'Male' | 'Female' | 'Other',
        ageMin: r.age_min != null ? String(r.age_min) : '',
        ageMax: r.age_max != null ? String(r.age_max) : '',
      })) ?? [],
  }
}

export function LabTestFormDialog({
  test,
  open,
  onOpenChange,
}: {
  test: LabTestSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createTest = useCreateLabTest()
  const updateTest = useUpdateLabTest()
  const isEditing = Boolean(test)

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TestFormValues>({ resolver: zodResolver(testFormSchema), defaultValues: toFormValues(test) })
  const { fields, append, remove } = useFieldArray({ control, name: 'ranges' })

  useEffect(() => {
    if (open) reset(toFormValues(test))
  }, [open, test, reset])

  async function onSubmit(values: TestFormValues) {
    const referenceRanges = values.ranges
      .filter((r) => r.min || r.max || r.unit || r.sex || r.ageMin || r.ageMax)
      .map((r) => ({
        min: r.min ? Number(r.min) : null,
        max: r.max ? Number(r.max) : null,
        unit: r.unit || null,
        sex: (r.sex || null) as 'Male' | 'Female' | 'Other' | null,
        age_min: r.ageMin ? Number(r.ageMin) : null,
        age_max: r.ageMax ? Number(r.ageMax) : null,
      }))

    const payload = {
      name: values.name,
      test_code: values.testCode || undefined,
      category: values.category || undefined,
      specimen_type: values.specimenType || undefined,
      turnaround_hours: values.turnaroundHours ? Number(values.turnaroundHours) : undefined,
      price: values.price || undefined,
      reference_ranges: referenceRanges,
    }

    try {
      if (test) {
        await updateTest.mutateAsync({ testId: test.id, payload })
        toast.success('Test updated')
      } else {
        await createTest.mutateAsync(payload)
        toast.success('Test added to catalog')
      }
      onOpenChange(false)
    } catch (error) {
      toast.error(`Could not ${isEditing ? 'update' : 'create'} test`, { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit lab test' : 'Add lab test'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Name *</Label>
              <Input id="name" {...register('name')} />
              {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="testCode">Test code</Label>
              <Input id="testCode" {...register('testCode')} />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="category">Category</Label>
              <Input id="category" {...register('category')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="specimenType">Specimen</Label>
              <Input id="specimenType" placeholder="Blood" {...register('specimenType')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="turnaroundHours">Turnaround (hrs)</Label>
              <Input id="turnaroundHours" type="number" min={0} step="1" {...register('turnaroundHours')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="price">Price</Label>
              <Input id="price" type="number" min={0} step="0.01" {...register('price')} />
              {errors.price && <p className="text-sm text-destructive">{errors.price.message}</p>}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Reference ranges (optional)</Label>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Leave sex/age blank for a range that applies to everyone. Multiple rows let one test have different ranges
              per sex or age group — the first matching row is used.
            </p>
            {fields.map((field, index) => (
              <div key={field.id} className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 p-2 sm:grid-cols-6 dark:border-slate-800">
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Min</Label>
                  <Input type="number" step="any" {...register(`ranges.${index}.min`)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Max</Label>
                  <Input type="number" step="any" {...register(`ranges.${index}.max`)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Unit</Label>
                  <Input {...register(`ranges.${index}.unit`)} />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Sex</Label>
                  <Controller
                    control={control}
                    name={`ranges.${index}.sex`}
                    render={({ field: f }) => (
                      <Select value={f.value ?? ''} onValueChange={(v) => f.onChange(v ?? '')}>
                        <SelectTrigger className="w-full">
                          <SelectValue placeholder="Any" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="">Any</SelectItem>
                          <SelectItem value="Male">Male</SelectItem>
                          <SelectItem value="Female">Female</SelectItem>
                          <SelectItem value="Other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Label className="text-xs">Age min</Label>
                  <Input type="number" min={0} step="any" {...register(`ranges.${index}.ageMin`)} />
                </div>
                <div className="flex items-end gap-1">
                  <div className="flex flex-1 flex-col gap-1">
                    <Label className="text-xs">Age max</Label>
                    <Input type="number" min={0} step="any" {...register(`ranges.${index}.ageMax`)} />
                  </div>
                  <Button type="button" variant="ghost" size="icon-sm" onClick={() => remove(index)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="w-fit gap-1.5" onClick={() => append({ ...EMPTY_RANGE_ROW })}>
              <Plus className="size-3.5" />
              Add range
            </Button>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : isEditing ? 'Save changes' : 'Add test'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
