import { ArrowRight, Loader2, Play, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useStartConsultation } from '@/features/consultations/hooks'
import { useDoctorOpdQueue, type OpdQueueRow } from '@/features/opd/use-doctor-queue'
import { getErrorMessage } from '@/lib/errors'

const QUEUE_STATUS_VARIANT: Record<string, string> = {
  WAITING: 'bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300',
  CALLED: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  IN_PROGRESS: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
}

function formatAge(dateOfBirth: string | null | undefined): string {
  if (!dateOfBirth) return ''
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

function QueueActionCell({ row }: { row: OpdQueueRow }) {
  const navigate = useNavigate()
  const startConsultation = useStartConsultation()

  if (!row.encounter) {
    return <Loader2 className="size-4 animate-spin text-muted-foreground" />
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
    <Badge variant="outline" className="text-muted-foreground">
      {row.encounter.status}
    </Badge>
  )
}

export function OpdQueuePage() {
  const { user } = useAuth()
  const { rows, isLoading, isFetching, refetch } = useDoctorOpdQueue(user?.id)

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">OPD Queue</h1>
          <p className="text-sm text-muted-foreground">Your active patients today. Refreshes automatically.</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void refetch()}>
          <RefreshCw className={`size-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="rounded-lg border border-border bg-card">
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
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                  No patients waiting in your queue right now.
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              rows.map((row) => (
                <TableRow key={row.token.id}>
                  <TableCell className="font-mono font-medium">#{row.token.token_number}</TableCell>
                  <TableCell className="font-medium">
                    {row.patient ? (
                      [row.patient.first_name, row.patient.last_name].filter(Boolean).join(' ')
                    ) : (
                      <Skeleton className="h-4 w-28" />
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {row.patient ? `${formatAge(row.patient.date_of_birth)} ${row.patient.gender ?? ''}`.trim() || '—' : ''}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`border-transparent ${QUEUE_STATUS_VARIANT[row.token.status] ?? ''}`}>
                      {row.token.status}
                    </Badge>
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
