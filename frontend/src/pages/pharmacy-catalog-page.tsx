import { AlertTriangle, PackagePlus, Pill, Plus } from 'lucide-react'
import { useState } from 'react'
import { PharmacyTabs } from '@/components/pharmacy/pharmacy-tabs'
import { MedicineFormDialog } from '@/components/pharmacy/medicine-form-dialog'
import { ReceiveStockDialog } from '@/components/pharmacy/receive-stock-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useMedicineCatalog } from '@/features/pharmacy/hooks'
import type { MedicineSummary } from '@/features/pharmacy/types'
import { useDebouncedValue } from '@/lib/use-debounced-value'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function PharmacyCatalogPage() {
  const { hasPermission } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [stockDialogMedicine, setStockDialogMedicine] = useState<MedicineSummary | null>(null)
  const [editingMedicine, setEditingMedicine] = useState<MedicineSummary | null>(null)

  const debouncedTerm = useDebouncedValue(searchTerm, 350)
  const { data, isLoading } = useMedicineCatalog({ q: debouncedTerm, lowStockOnly, limit: 50 })
  const medicines = data?.items ?? []

  const canManage = hasPermission('pharmacy.manage_catalog')

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Pharmacy</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Medicine catalog and stock.</p>
        </div>
        {canManage && (
          <Button
            className="gap-1.5"
            onClick={() => {
              setEditingMedicine(null)
              setFormOpen(true)
            }}
          >
            <Plus className="size-4" />
            Add medicine
          </Button>
        )}
      </div>

      <PharmacyTabs />

      <div className="flex flex-wrap items-center gap-4">
        <Input
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="Search by name or generic name…"
          className="max-w-sm"
        />
        <div className="flex items-center gap-2">
          <Checkbox id="lowStockOnly" checked={lowStockOnly} onCheckedChange={(checked) => setLowStockOnly(checked === true)} />
          <Label htmlFor="lowStockOnly" className="font-normal">
            Low stock only
          </Label>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Form / Strength</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">Stock</TableHead>
              <TableHead>Status</TableHead>
              {canManage && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: canManage ? 6 : 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && medicines.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={canManage ? 6 : 5}>
                  <EmptyState
                    icon={Pill}
                    title="No medicines found"
                    description={canManage ? 'Add a medicine to start building your catalog.' : 'The catalog is empty right now.'}
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              medicines.map((medicine) => (
                <TableRow key={medicine.id}>
                  <TableCell>
                    <p className="font-medium text-slate-900 dark:text-slate-100">{medicine.name}</p>
                    {medicine.generic_name && <p className="text-xs text-slate-500 dark:text-slate-400">{medicine.generic_name}</p>}
                  </TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">
                    {[medicine.dosage_form, medicine.strength].filter(Boolean).join(' · ') || '—'}
                  </TableCell>
                  <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(medicine.unit_price)}</TableCell>
                  <TableCell className="text-right">
                    <span className="flex items-center justify-end gap-1.5 font-medium text-slate-900 dark:text-slate-100">
                      {medicine.is_below_reorder_threshold && <AlertTriangle className="size-3.5 text-amber-500" />}
                      {medicine.total_stock}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={medicine.is_active ? 'secondary' : 'outline'}>{medicine.is_active ? 'Active' : 'Inactive'}</Badge>
                  </TableCell>
                  {canManage && (
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button variant="ghost" size="sm" onClick={() => setStockDialogMedicine(medicine)}>
                          <PackagePlus className="size-3.5" />
                          Stock
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingMedicine(medicine)
                            setFormOpen(true)
                          }}
                        >
                          Edit
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      <MedicineFormDialog medicine={editingMedicine} open={formOpen} onOpenChange={setFormOpen} />
      <ReceiveStockDialog
        medicine={stockDialogMedicine}
        open={stockDialogMedicine !== null}
        onOpenChange={(open) => !open && setStockDialogMedicine(null)}
      />
    </div>
  )
}
