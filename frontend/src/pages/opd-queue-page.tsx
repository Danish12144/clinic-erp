import { Activity, ArrowRight, ClipboardList, IndianRupee, Loader2, Play, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { CollectConsultationFeeDialog } from '@/components/opd/collect-consultation-fee-dialog'
import { RecordVitalsDialog } from '@/components/opd/record-vitals-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useStartConsultation } from '@/features/consultations/hooks'
import { useDoctorDirectory } from '@/features/doctors/hooks'
import { useDoctorOpdQueue, type OpdQueueRow } from '@/features/opd/use-doctor-queue'
import { getErrorMessage } from '@/lib/errors'

const BILLABLE_ENCOUNTER_STATUSES = new Set(['OPEN', 'IN_CONSULTATION', 'COMPLETED'])

export interface BillingTarget {
  encounterId: string
  patientId: string
  branchId: string
  patientName: string
  defaultAmount: string | null
}

function formatAge(dateOfBirth: string | null | undefined): string {
  if (!dateOfBirth) return ''
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

// canManageConsultation is Doctor/Owner (consultation.manage) -- they get
// the existing Start/Continue flow into the full clinical pad. Anyone
// else who reached this page holds either vitals.record (Nurse by
// default, or any role an Owner has granted it to via a permission
// override) or only queue.view (Receptionist by default — monitor tokens
// read-only, no vitals-recording permission at all). canRecordVitals is
// checked explicitly here rather than inferred from "not
// canManageConsultation," so a view-only caller sees a plain status badge
// instead of a "Record vitals" button that would just 403 on click. See
// OpdQueuePage's own comment for why this page serves all three audiences.
function ConsultationAction({ row, canManageConsultation, canRecordVitals, onRecordVitals }: {
  row: OpdQueueRow
  canManageConsultation: boolean
  canRecordVitals: boolean
  onRecordVitals: (encounterId: string) => void
}) {
  const navigate = useNavigate()
  const startConsultation = useStartConsultation()

  if (!row.encounter) {
    return <Loader2 className="size-4 animate-spin text-slate-400" />
  }

  if (!canManageConsultation) {
    if (canRecordVitals && (row.encounter.status === 'OPEN' || row.encounter.status === 'IN_CONSULTATION')) {
      return (
        <Button size="sm" variant="outline" className="gap-1" onClick={() => onRecordVitals(row.encounter!.id)}>
          <Activity className="size-3.5" />
          Record vitals
        </Button>
      )
    }
    return (
      <Badge variant="outline" className="text-slate-500">
        {row.encounter.status}
      </Badge>
    )
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

// canManageConsultation/canRecordVitals each render at most one action
// (see ConsultationAction); canBill (billing.manage — Owner/Receptionist)
// is independent of both, so it renders alongside whichever one applies —
// a Receptionist who only holds queue.view (no vitals.record) still gets
// to collect the consultation fee for a waiting patient, the whole point
// of this "pay first, see the doctor after" front-desk workflow.
function QueueActionCell({
  row,
  canManageConsultation,
  canRecordVitals,
  canBill,
  onRecordVitals,
  onCollectFee,
}: {
  row: OpdQueueRow
  canManageConsultation: boolean
  canRecordVitals: boolean
  canBill: boolean
  onRecordVitals: (encounterId: string) => void
  onCollectFee: (row: OpdQueueRow) => void
}) {
  return (
    <div className="flex items-center justify-end gap-2">
      {canBill && row.encounter && BILLABLE_ENCOUNTER_STATUSES.has(row.encounter.status) && (
        <Button size="sm" variant="outline" className="gap-1" onClick={() => onCollectFee(row)}>
          <IndianRupee className="size-3.5" />
          Collect fee
        </Button>
      )}
      <ConsultationAction row={row} canManageConsultation={canManageConsultation} canRecordVitals={canRecordVitals} onRecordVitals={onRecordVitals} />
    </div>
  )
}

export function OpdQueuePage() {
  const { user, hasPermission } = useAuth()
  // consultation.manage holders (Doctor/Owner) see their own queue, same
  // as before. Anyone else who reached this page (Nurse by default, or
  // Receptionist/any role via queue.view or a vitals.record override) has
  // no "own queue" concept — there's no consultation to be "theirs" — so
  // they see the whole branch's active queue instead (useDoctorOpdQueue
  // (undefined) omits the doctor_id filter entirely).
  const canManageConsultation = hasPermission('consultation.manage')
  const canRecordVitals = hasPermission('vitals.record')
  const canBill = hasPermission('billing.manage')
  const { rows, isLoading, isFetching, refetch } = useDoctorOpdQueue(canManageConsultation ? user?.id : undefined)
  const [vitalsEncounterId, setVitalsEncounterId] = useState<string | null>(null)
  const [billingTarget, setBillingTarget] = useState<BillingTarget | null>(null)
  const { data: doctorDirectory } = useDoctorDirectory()

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">OPD Queue</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {canManageConsultation
              ? 'Your active patients today.'
              : canRecordVitals
                ? "Today's active patients, clinic-wide."
                : "Today's active patients, clinic-wide — view only."}{' '}
            Refreshes automatically.
          </p>
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
                    <QueueActionCell
                      row={row}
                      canManageConsultation={canManageConsultation}
                      canRecordVitals={canRecordVitals}
                      canBill={canBill}
                      onRecordVitals={setVitalsEncounterId}
                      onCollectFee={(billingRow) => {
                        if (!billingRow.encounter) return
                        const doctor = doctorDirectory?.items.find((d) => d.user_id === billingRow.token.doctor_id)
                        setBillingTarget({
                          encounterId: billingRow.encounter.id,
                          patientId: billingRow.encounter.patient_id,
                          branchId: billingRow.encounter.branch_id,
                          patientName: billingRow.patient
                            ? [billingRow.patient.first_name, billingRow.patient.last_name].filter(Boolean).join(' ')
                            : 'this patient',
                          defaultAmount: doctor?.consultation_fee ?? null,
                        })
                      }}
                    />
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      <RecordVitalsDialog encounterId={vitalsEncounterId} open={Boolean(vitalsEncounterId)} onOpenChange={(open) => !open && setVitalsEncounterId(null)} />
      {billingTarget && (
        <CollectConsultationFeeDialog
          encounterId={billingTarget.encounterId}
          patientId={billingTarget.patientId}
          branchId={billingTarget.branchId}
          patientName={billingTarget.patientName}
          defaultAmount={billingTarget.defaultAmount}
          open={billingTarget !== null}
          onOpenChange={(open) => !open && setBillingTarget(null)}
        />
      )}
    </div>
  )
}
