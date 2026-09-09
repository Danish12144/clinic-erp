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
import { useCreateInventoryItem, useUpdateInventoryItem } from '@/features/inventory/hooks'
import { INVENTORY_ITEM_CATEGORIES, INVENTORY_UNITS, type InventoryItemSummary } from '@/features/inventory/types'
import { getErrorMessage } from '@/lib/errors'

const itemFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(300),
  category: z.enum(INVENTORY_ITEM_CATEGORIES),
  unit: z.enum(INVENTORY_UNITS),
  minReorderLevel: z.string().refine((v) => !v || Number(v) >= 0, 'Must be 0 or more'),
  costPerUnit: z.string().refine((v) => !v || Number(v) >= 0, 'Must be 0 or more'),
})

type ItemFormValues = z.infer<typeof itemFormSchema>

function toFormValues(item: InventoryItemSummary | null): ItemFormValues {
  return {
    name: item?.name ?? '',
    category: item?.category ?? 'CONSUMABLE',
    unit: item?.unit ?? 'PIECES',
    minReorderLevel: item?.min_reorder_level ?? '0',
    costPerUnit: item?.cost_per_unit ?? '0',
  }
}

export function InventoryItemFormDialog({
  item,
  open,
  onOpenChange,
}: {
  item: InventoryItemSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const createItem = useCreateInventoryItem()
  const updateItem = useUpdateInventoryItem()
  const isEditing = Boolean(item)

  const {
    register,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<ItemFormValues>({ resolver: zodResolver(itemFormSchema), defaultValues: toFormValues(item) })

  useEffect(() => {
    if (open) reset(toFormValues(item))
  }, [open, item, reset])

  async function onSubmit(values: ItemFormValues) {
    try {
      if (item) {
        await updateItem.mutateAsync({
          itemId: item.id,
          payload: {
            name: values.name,
            category: values.category,
            unit: values.unit,
            min_reorder_level: values.minReorderLevel,
            cost_per_unit: values.costPerUnit,
          },
        })
        toast.success('Item updated')
      } else {
        await createItem.mutateAsync({
          name: values.name,
          category: values.category,
          unit: values.unit,
          min_reorder_level: values.minReorderLevel,
          cost_per_unit: values.costPerUnit,
        })
        toast.success('Item added')
      }
      onOpenChange(false)
    } catch (error) {
      toast.error(`Could not ${isEditing ? 'update' : 'create'} item`, { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit item' : 'Add inventory item'}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="itemName">Name *</Label>
            <Input id="itemName" {...register('name')} />
            {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>Category</Label>
              <Select value={watch('category')} onValueChange={(value) => value && setValue('category', value as ItemFormValues['category'])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INVENTORY_ITEM_CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Unit</Label>
              <Select value={watch('unit')} onValueChange={(value) => value && setValue('unit', value as ItemFormValues['unit'])}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INVENTORY_UNITS.map((u) => (
                    <SelectItem key={u} value={u}>
                      {u}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="minReorderLevel">Reorder at</Label>
              <Input id="minReorderLevel" type="number" min={0} step="0.01" {...register('minReorderLevel')} />
              {errors.minReorderLevel && <p className="text-sm text-destructive">{errors.minReorderLevel.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="costPerUnit">Cost per unit</Label>
              <Input id="costPerUnit" type="number" min={0} step="0.01" {...register('costPerUnit')} />
              {errors.costPerUnit && <p className="text-sm text-destructive">{errors.costPerUnit.message}</p>}
            </div>
          </div>
          {!isEditing && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              New items start with zero stock — receive stock with a Purchase transaction after creating.
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : isEditing ? 'Save changes' : 'Add item'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
