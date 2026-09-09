import { useQueries } from '@tanstack/react-query'
import { FileText, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { NewInvoiceDialog } from '@/components/billing/new-invoice-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useInvoiceSearch } from '@/features/billing/hooks'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'

const STATUS_OPTIONS = ['DRAFT', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'VOID'] as const

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function BillingPage() {
  const { hasPermission } = useAuth()
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const [newInvoiceOpen, setNewInvoiceOpen] = useState(false)

  const { data, isLoading } = useInvoiceSearch({ status: statusFilter, limit: 30 })
  const invoices = data?.items ?? []

  const patientIds = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((inv) => inv.patient_id))),
    [data?.items],
  )
  const patientQueries = useQueries({
    queries: patientIds.map((id) => ({
      queryKey: ['patients', 'get', id],
      queryFn: () => getPatient(id),
      staleTime: 60_000,
    })),
  })
  const patientsById = useMemo(() => {
    const map = new Map<string, PatientSummary>()
    for (const q of patientQueries) {
      if (q.data) map.set(q.data.id, q.data)
    }
    return map
  }, [patientQueries])

  const canCreate = hasPermission('billing.manage')

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Billing</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Invoices and payments.</p>
        </div>
        {canCreate && (
          <Button className="gap-1.5" onClick={() => setNewInvoiceOpen(true)}>
            <Plus className="size-4" />
            New invoice
          </Button>
        )}
      </div>

      <Select value={statusFilter ?? 'ALL'} onValueChange={(value) => setStatusFilter(value === 'ALL' ? undefined : (value ?? undefined))}>
        <SelectTrigger className="w-full sm:w-48">
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ALL">All statuses</SelectItem>
          {STATUS_OPTIONS.map((status) => (
            <SelectItem key={status} value={status}>
              <StatusBadge status={status} />
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Patient</TableHead>
              <TableHead>Total</TableHead>
              <TableHead>Balance due</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-28" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && invoices.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5}>
                  <EmptyState
                    icon={FileText}
                    title="No invoices found"
                    description={canCreate ? 'Create a new invoice to get started.' : 'Invoices will show up here once created.'}
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              invoices.map((invoice) => {
                const patient = patientsById.get(invoice.patient_id)
                return (
                  <TableRow key={invoice.id} className="cursor-pointer" onClick={() => navigate(`/billing/${invoice.id}`)}>
                    <TableCell className="font-medium text-slate-900 dark:text-slate-100">
                      {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-4 w-24" />}
                    </TableCell>
                    <TableCell className="text-slate-700 dark:text-slate-300">{formatMoney(invoice.total)}</TableCell>
                    <TableCell className="font-medium text-slate-900 dark:text-slate-100">{formatMoney(invoice.balance_due)}</TableCell>
                    <TableCell>
                      <StatusBadge status={invoice.status} />
                    </TableCell>
                    <TableCell className="text-slate-500 dark:text-slate-400">
                      {new Date(invoice.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                )
              })}
          </TableBody>
        </Table>
      </div>

      <NewInvoiceDialog open={newInvoiceOpen} onOpenChange={setNewInvoiceOpen} />
    </div>
  )
}
