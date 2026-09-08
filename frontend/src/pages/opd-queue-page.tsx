import { ArrowRight, ClipboardList, Loader2, Play, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useStartConsultation } from '@/features/consultations/hooks'
import { useDoctorOpdQueue, type OpdQueueRow } from '@/features/opd/use-doctor-queue'
import { getErrorMessage } from '@/lib/errors'

function formatAge(dateOfBirth: string | null | undefined): string {
  if (!dateOfBirth) return ''
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

function QueueActionCell({ row }: { row: OpdQueueRow }) {
  const navigate = useNavigate()
  const startConsultation = useStartConsultation()

  if (!row.encounter) {
    return <Loader2 className="size-4 animate-spin text-slate-400" />
  }

  if (row.encounter.status === 'IN_CONSULTATION') {
    return (
      <Button size="sm" variant="secondary" className="gap-1" onClick={() => navigate(`/opd/${row.encounter!.id}`)}>
        Continue
        <ArrowRight className="size-3.5" />
      </Button>
    )
  }

  if (row.encounter.status === 'OPEN') {
    return (
      <Button
        size="sm"
        className="gap-1"
        disabled={startConsultation.isPending}
        onClick={async () => {
          try {
            await startConsultation.mutateAsync({ encounter_id: row.encounter!.id })
            navigate(`/opd/${row.encounter!.id}`)
          } catch (error) {
            toast.error('Could not start consultation', { description: getErrorMessage(error) })
          }
        }}
      >
        <Play className="size-3.5" />
        {startConsultation.isPending ? 'Starting…' : 'Start consultation'}
      </Button>
    )
  }

  return (
    <Badge variant="outline" className="text-slate-500">
      {row.encounter.status}
    </Badge>
  )
}

export function OpdQueuePage() {
  const { user } = useAuth()
  const { rows, isLoading, isFetching, refetch } = useDoctorOpdQueue(user?.id)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">OPD Queue</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Your active patients today. Refreshes automatically.</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void refetch()}>
          <RefreshCw className={`size-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-16">Token</TableHead>
              <TableHead>Patient</TableHead>
              <TableHead>Age / Gender</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && rows.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5}>
                  <EmptyState
                    icon={ClipboardList}
                    title="No patients waiting"
                    description="Your queue is empty right now — checked-in patients assigned to you will show up here."
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              rows.map((row) => (
                <TableRow key={row.token.id}>
                  <TableCell className="font-mono font-medium text-slate-900 dark:text-slate-100">
                    #{row.token.token_number}
                  </TableCell>
                  <TableCell className="font-medium text-slate-900 dark:text-slate-100">
                    {row.patient ? (
                      [row.patient.first_name, row.patient.last_name].filter(Boolean).join(' ')
                    ) : (
                      <Skeleton className="h-4 w-28" />
                    )}
                  </TableCell>
                  <TableCell className="text-slate-500 dark:text-slate-400">
                    {row.patient ? `${formatAge(row.patient.date_of_birth)} ${row.patient.gender ?? ''}`.trim() || '—' : ''}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={row.token.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    <QueueActionCell row={row} />
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
