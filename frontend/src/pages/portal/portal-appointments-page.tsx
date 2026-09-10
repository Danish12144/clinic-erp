import { CalendarClock, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { BookMyAppointmentDialog } from '@/components/portal/book-my-appointment-dialog'
import { CancelMyAppointmentDialog } from '@/components/portal/cancel-my-appointment-dialog'
import { RescheduleMyAppointmentDialog } from '@/components/portal/reschedule-my-appointment-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyAppointments } from '@/features/appointments/hooks'
import type { AppointmentSummary } from '@/features/appointments/types'

const NOT_CANCELLABLE = new Set(['CANCELLED', 'NO_SHOW'])

function isUpcoming(appointment: AppointmentSummary): boolean {
  return new Date(appointment.scheduled_at).getTime() >= Date.now() && appointment.status !== 'CANCELLED'
}

function AppointmentCard({
  appointment,
  onReschedule,
  onCancel,
}: {
  appointment: AppointmentSummary
  onReschedule: (appointment: AppointmentSummary) => void
  onCancel: (appointmentId: string) => void
}) {
  const when = new Date(appointment.scheduled_at)
  return (
    <Card size="sm">
      <CardContent className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
            {when.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
          </p>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {when.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })} · {appointment.duration_minutes} min
          </p>
          {appointment.notes && <p className="mt-1 text-xs text-slate-400 dark:text-slate-600">{appointment.notes}</p>}
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={appointment.status} />
          {appointment.status === 'SCHEDULED' && (
            <Button variant="outline" size="sm" onClick={() => onReschedule(appointment)}>
              Reschedule
            </Button>
          )}
          {!NOT_CANCELLABLE.has(appointment.status) && (
            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => onCancel(appointment.id)}>
              Cancel
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function PortalAppointmentsPage() {
  const { data, isLoading } = useMyAppointments()
  const [bookOpen, setBookOpen] = useState(false)
  const [rescheduleTarget, setRescheduleTarget] = useState<AppointmentSummary | null>(null)
  const [cancelTargetId, setCancelTargetId] = useState<string | null>(null)

  const { upcoming, past } = useMemo(() => {
    const items = data?.items ?? []
    const sorted = [...items].sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
    return {
      upcoming: sorted.filter(isUpcoming),
      past: sorted.filter((a) => !isUpcoming(a)).reverse(),
    }
  }, [data])

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">My appointments</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Book, reschedule, or cancel your visits.</p>
        </div>
        <Button className="gap-1.5" onClick={() => setBookOpen(true)}>
          <Plus className="size-4" />
          Book appointment
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : upcoming.length === 0 && past.length === 0 ? (
        <EmptyState icon={CalendarClock} title="No appointments yet" description="Book your first appointment to get started." />
      ) : (
        <>
          {upcoming.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Upcoming</h2>
              {upcoming.map((appointment) => (
                <AppointmentCard
                  key={appointment.id}
                  appointment={appointment}
                  onReschedule={setRescheduleTarget}
                  onCancel={setCancelTargetId}
                />
              ))}
            </div>
          )}
          {past.length > 0 && (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Past</h2>
              {past.map((appointment) => (
                <AppointmentCard
                  key={appointment.id}
                  appointment={appointment}
                  onReschedule={setRescheduleTarget}
                  onCancel={setCancelTargetId}
                />
              ))}
            </div>
          )}
        </>
      )}

      <BookMyAppointmentDialog open={bookOpen} onOpenChange={setBookOpen} />
      <RescheduleMyAppointmentDialog appointment={rescheduleTarget} open={Boolean(rescheduleTarget)} onOpenChange={(open) => !open && setRescheduleTarget(null)} />
      <CancelMyAppointmentDialog appointmentId={cancelTargetId} open={Boolean(cancelTargetId)} onOpenChange={(open) => !open && setCancelTargetId(null)} />
    </div>
  )
}
