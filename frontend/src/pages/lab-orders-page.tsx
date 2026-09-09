import { useQueries } from '@tanstack/react-query'
import { FlaskConical } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LabTabs } from '@/components/lab/lab-tabs'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { LAB_ORDER_STATUSES } from '@/features/lab/types'
import { useLabOrders } from '@/features/lab/hooks'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'

export function LabOrdersPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const { data, isLoading } = useLabOrders({ status: statusFilter, limit: 50 })
  const orders = data?.items ?? []

  const patientIds = useMemo(() => Array.from(new Set((data?.items ?? []).map((o) => o.patient_id))), [data?.items])
  const patientQueries = useQueries({
    queries: patientIds.map((id) => ({ queryKey: ['patients', 'get', id], queryFn: () => getPatient(id), staleTime: 60_000 })),
  })
  const patientsById = useMemo(() => {
    const map = new Map<string, PatientSummary>()
    for (const q of patientQueries) if (q.data) map.set(q.data.id, q.data)
    return map
  }, [patientQueries])

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Lab</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Orders awaiting sample collection, results, or finalization.</p>
      </div>

      <LabTabs />

      <Select value={statusFilter ?? 'ALL'} onValueChange={(value) => setStatusFilter(value === 'ALL' ? undefined : (value ?? undefined))}>
        <SelectTrigger className="w-full sm:w-56">
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="ALL">All statuses</SelectItem>
          {LAB_ORDER_STATUSES.map((status) => (
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
              <TableHead>Test</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ordered</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 4 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-28" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && orders.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={4}>
                  <EmptyState icon={FlaskConical} title="No lab orders found" description="Orders placed from a consultation will show up here." />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              orders.map((order) => {
                const patient = patientsById.get(order.patient_id)
                return (
                  <TableRow key={order.id} className="cursor-pointer" onClick={() => navigate(`/lab/orders/${order.id}`)}>
                    <TableCell className="font-medium text-slate-900 dark:text-slate-100">
                      {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-4 w-24" />}
                    </TableCell>
                    <TableCell className="text-slate-700 dark:text-slate-300">{order.test.name}</TableCell>
                    <TableCell>
                      <StatusBadge status={order.status} />
                    </TableCell>
                    <TableCell className="text-slate-500 dark:text-slate-400">{new Date(order.ordered_at).toLocaleString()}</TableCell>
                  </TableRow>
                )
              })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
