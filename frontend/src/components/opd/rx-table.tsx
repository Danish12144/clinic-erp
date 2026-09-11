import { Check, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Controller, useFieldArray, useWatch, type Control, type UseFormSetValue } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useMedicineSearch } from '@/features/pharmacy/hooks'
import { EMPTY_RX_ITEM, type ConsultationFormValues } from '@/components/opd/consultation-form-schema'

function MedicineAutocompleteCell({
  index,
  control,
  setValue,
}: {
  index: number
  control: Control<ConsultationFormValues>
  setValue: UseFormSetValue<ConsultationFormValues>
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const { data, isFetching } = useMedicineSearch(query)
  const suggestions = data?.items ?? []
  // Shown as a small confirmation once a catalog suggestion is actually
  // picked — otherwise this row stays free-text-only and Pharmacy won't be
  // able to dispense it against inventory later (see pharmacy-dispense-
  // page.tsx's own "Not catalog-linked" badge, the other half of this).
  const linkedMedicineId = useWatch({ control, name: `items.${index}.medicineId` })

  return (
    <div className="relative">
      <Controller
        control={control}
        name={`items.${index}.medicineLabel`}
        render={({ field }) => (
          <div className="relative">
            <Input
              {...field}
              placeholder="Medicine name"
              autoComplete="off"
              className={linkedMedicineId ? 'pr-7' : undefined}
              onChange={(event) => {
                field.onChange(event.target.value)
                setQuery(event.target.value)
                setValue(`items.${index}.medicineId`, undefined)
                setOpen(true)
              }}
              onFocus={() => setOpen(true)}
              onBlur={() => {
                // Let a mousedown-selected suggestion register before closing.
                setTimeout(() => setOpen(false), 150)
              }}
            />
            {linkedMedicineId && (
              <Check
                className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-emerald-600 dark:text-emerald-400"
                aria-label="Linked to catalog medicine — dispensable"
              />
            )}
          </div>
        )}
      />
      {open && query.trim().length >= 2 && (isFetching || suggestions.length > 0) && (
        <div className="absolute z-20 mt-1 max-h-48 w-64 overflow-y-auto rounded-md border border-border bg-popover shadow-md">
          {isFetching && <p className="px-2 py-1.5 text-xs text-muted-foreground">Searching…</p>}
          {!isFetching &&
            suggestions.map((medicine) => (
              <button
                key={medicine.id}
                type="button"
                className="block w-full px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                onMouseDown={(event) => {
                  event.preventDefault()
                  setValue(`items.${index}.medicineId`, medicine.id)
                  setValue(`items.${index}.medicineLabel`, medicine.name)
                  setOpen(false)
                }}
              >
                {medicine.name}
                {medicine.strength ? ` (${medicine.strength})` : ''}
                {medicine.dosage_form ? ` — ${medicine.dosage_form}` : ''}
              </button>
            ))}
        </div>
      )}
    </div>
  )
}

export function RxTable({
  control,
  setValue,
  errorMessage,
}: {
  control: Control<ConsultationFormValues>
  setValue: UseFormSetValue<ConsultationFormValues>
  errorMessage?: string
}) {
  const { fields, append, remove } = useFieldArray({ control, name: 'items' })

  return (
    <div className="flex flex-col gap-2">
      <datalist id="route-suggestions">
        <option value="Oral" />
        <option value="Topical" />
        <option value="IV" />
        <option value="IM" />
        <option value="SC" />
        <option value="Inhalation" />
      </datalist>

      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-48">Medicine</TableHead>
              <TableHead className="w-28">Dosage</TableHead>
              <TableHead className="w-28">Frequency</TableHead>
              <TableHead className="w-24">Duration</TableHead>
              <TableHead className="w-28">Route</TableHead>
              <TableHead className="w-20">Qty</TableHead>
              <TableHead className="min-w-40">Instructions</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {fields.map((field, index) => (
              <TableRow key={field.id}>
                <TableCell>
                  <MedicineAutocompleteCell index={index} control={control} setValue={setValue} />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.dosage`}
                    render={({ field: f }) => <Input {...f} placeholder="500mg" />}
                  />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.frequency`}
                    render={({ field: f }) => <Input {...f} placeholder="1-0-1" />}
                  />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.duration`}
                    render={({ field: f }) => <Input {...f} placeholder="5 days" />}
                  />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.route`}
                    render={({ field: f }) => <Input {...f} list="route-suggestions" placeholder="Oral" />}
                  />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.prescribedQuantity`}
                    render={({ field: f }) => <Input {...f} type="number" min={1} max={10000} />}
                  />
                </TableCell>
                <TableCell>
                  <Controller
                    control={control}
                    name={`items.${index}.instructions`}
                    render={({ field: f }) => <Input {...f} placeholder="After food" />}
                  />
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={fields.length === 1}
                    onClick={() => remove(index)}
                  >
                    <X className="size-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-fit gap-1.5"
        onClick={() => append({ ...EMPTY_RX_ITEM })}
      >
        <Plus className="size-3.5" />
        Add medicine
      </Button>
    </div>
  )
}
