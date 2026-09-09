import { AlertTriangle, Boxes, Plus } from 'lucide-react'
import { useState } from 'react'
import { InventoryItemFormDialog } from '@/components/inventory/inventory-item-form-dialog'
import { InventoryTransactionDialog } from '@/components/inventory/inventory-transaction-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useInventoryItems } from '@/features/inventory/hooks'
import { INVENTORY_ITEM_CATEGORIES, type InventoryItemCategory, type InventoryItemSummary } from '@/features/inventory/types'

export function InventoryPage() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('inventory.manage')
  const canRecordUsage = hasPermission('inventory.record_usage')
  const canRecordTransaction = canManage || canRecordUsage

  const [category, setCategory] = useState<InventoryItemCategory | ''>('')
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [formItem, setFormItem] = useState<InventoryItemSummary | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [transactionItem, setTransactionItem] = useState<InventoryItemSummary | null>(null)

  const { data, isLoading } = useInventoryItems({ category: category || undefined, lowStockOnly, limit: 50 })
  const items = data?.items ?? []

  const columnCount = 5 + (canManage ? 1 : 0) + (canRecordTransaction ? 1 : 0)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Inventory</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Consumables, equipment, and general clinic supplies.</p>
        </div>
        {canManage && (
          <Button
            className="gap-1.5"
            onClick={() => {
              setFormItem(null)
              setFormOpen(true)
            }}
          >
            <Plus className="size-4" />
            Add item
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Select value={category || 'ALL'} onValueChange={(value) => setCategory(value === 'ALL' ? '' : ((value ?? '') as InventoryItemCategory))}>
          <SelectTrigger className="w-full sm:w-48">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All categories</SelectItem>
            {INVENTORY_ITEM_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
              <TableHead>Category</TableHead>
              <TableHead className="text-right">Stock</TableHead>
              <TableHead className="text-right">Cost/unit</TableHead>
              <TableHead>Status</TableHead>
              {canManage && <TableHead>Active</TableHead>}
              {canRecordTransaction && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: columnCount }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && items.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columnCount}>
                  <EmptyState
                    icon={Boxes}
                    title="No items found"
                    description={canManage ? 'Add an item to start tracking stock.' : 'No inventory items match these filters.'}
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-medium text-slate-900 dark:text-slate-100">{item.name}</TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{item.category}</TableCell>
                  <TableCell className="text-right">
                    <span className="flex items-center justify-end gap-1.5 font-medium text-slate-900 dark:text-slate-100">
                      {item.is_below_reorder_level && <AlertTriangle className="size-3.5 text-amber-500" />}
                      {item.current_stock} {item.unit}
                    </span>
                  </TableCell>
                  <TableCell className="text-right text-slate-700 dark:text-slate-300">
                    ₹{Number(item.cost_per_unit).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell>
                    {item.is_below_reorder_level ? (
                      <Badge variant="outline" className="border-amber-300 text-amber-700 dark:text-amber-400">
                        Low stock
                      </Badge>
                    ) : (
                      <span className="text-xs text-slate-400 dark:text-slate-500">OK</span>
                    )}
                  </TableCell>
                  {canManage && (
                    <TableCell>
                      <Badge variant={item.is_active ? 'secondary' : 'outline'}>{item.is_active ? 'Active' : 'Inactive'}</Badge>
                    </TableCell>
                  )}
                  {canRecordTransaction && (
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button variant="ghost" size="sm" onClick={() => setTransactionItem(item)}>
                          Log transaction
                        </Button>
                        {canManage && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setFormItem(item)
                              setFormOpen(true)
                            }}
                          >
                            Edit
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      <InventoryItemFormDialog item={formItem} open={formOpen} onOpenChange={setFormOpen} />
      <InventoryTransactionDialog item={transactionItem} open={transactionItem !== null} onOpenChange={(open) => !open && setTransactionItem(null)} />
    </div>
  )
}
