import { FlaskConical, Plus } from 'lucide-react'
import { useState } from 'react'
import { LabTabs } from '@/components/lab/lab-tabs'
import { LabTestFormDialog } from '@/components/lab/lab-test-form-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useLabTestCatalog } from '@/features/lab/hooks'
import type { LabTestSummary } from '@/features/lab/types'
import { useDebouncedValue } from '@/lib/use-debounced-value'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function LabCatalogPage() {
  const { hasPermission } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingTest, setEditingTest] = useState<LabTestSummary | null>(null)

  const debouncedTerm = useDebouncedValue(searchTerm, 350)
  const { data, isLoading, isError } = useLabTestCatalog({ q: debouncedTerm, limit: 50 })
  const tests = data?.items ?? []
  const canManage = hasPermission('lab.manage_catalog')

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Lab</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Test catalog and reference ranges.</p>
        </div>
        {canManage && (
          <Button
            className="gap-1.5"
            onClick={() => {
              setEditingTest(null)
              setFormOpen(true)
            }}
          >
            <Plus className="size-4" />
            Add test
          </Button>
        )}
      </div>

      <LabTabs />

      {isError ? (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
          Lab isn't enabled for this clinic yet. Ask your Owner to turn on <code>features.lab_enabled</code> in clinic
          settings.
        </p>
      ) : (
        <>
          <Input value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search tests…" className="max-w-sm" />

          <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Category / Specimen</TableHead>
                  <TableHead>Turnaround</TableHead>
                  <TableHead className="text-right">Price</TableHead>
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

                {!isLoading && tests.length === 0 && (
                  <TableRow className="hover:bg-transparent">
                    <TableCell colSpan={canManage ? 6 : 5}>
                      <EmptyState
                        icon={FlaskConical}
                        title="No tests found"
                        description={canManage ? 'Add a test to start building your catalog.' : 'The test catalog is empty right now.'}
                      />
                    </TableCell>
                  </TableRow>
                )}

                {!isLoading &&
                  tests.map((test) => (
                    <TableRow key={test.id}>
                      <TableCell>
                        <p className="font-medium text-slate-900 dark:text-slate-100">{test.name}</p>
                        {test.test_code && <p className="text-xs text-slate-500 dark:text-slate-400">{test.test_code}</p>}
                      </TableCell>
                      <TableCell className="text-slate-600 dark:text-slate-400">
                        {[test.category, test.specimen_type].filter(Boolean).join(' · ') || '—'}
                      </TableCell>
                      <TableCell className="text-slate-600 dark:text-slate-400">
                        {test.turnaround_hours != null ? `${test.turnaround_hours}h` : '—'}
                      </TableCell>
                      <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(test.price)}</TableCell>
                      <TableCell>
                        <Badge variant={test.is_active ? 'secondary' : 'outline'}>{test.is_active ? 'Active' : 'Inactive'}</Badge>
                      </TableCell>
                      {canManage && (
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEditingTest(test)
                              setFormOpen(true)
                            }}
                          >
                            Edit
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}

      <LabTestFormDialog test={editingTest} open={formOpen} onOpenChange={setFormOpen} />
    </div>
  )
}
