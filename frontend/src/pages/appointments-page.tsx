import { useQueries } from '@tanstack/react-query'
import { CalendarX2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { BookAppointmentDialog } from '@/components/appointments/book-appointment-dialog'
import { CancelAppointmentDialog } from '@/components/appointments/cancel-appointment-dialog'
import { RescheduleAppointmentDialog } from '@/components/appointments/reschedule-appointment-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useAppointmentSearch } from '@/features/appointments/hooks'
import type { AppointmentSummary } from '@/features/appointments/types'
import { useBranches } from '@/features/branches/hooks'
import { useBookableDoctors } from '@/features/doctors/hooks'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'
import { dayHoursFor, formatDateInput, generateTimeSlots, slotToDate, type TimeSlot } from '@/lib/working-hours'

const SLOT_INCREMENT_MINUTES = 15
const ACTIVE_APPOINTMENT_STATUSES = new Set(['SCHEDULED', 'CHECKED_IN', 'IN_PROGRESS'])

function startOfDay(date: Date): Date {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  return d
}

function endOfDay(date: Date): Date {
  const d = new Date(date)
  d.setHours(23, 59, 59, 999)
  return d
}

// A testing accommodation, mirroring the backend's own
// Settings.appointment_enforce_working_hours default-off relaxation: the
// slot grid below only ever offers times within the doctor's declared
// working hours, so there was no way to open the booking dialog at all
// outside that window. This button opens it pre-filled with "right now"
// regardless of working hours/day availability — the backend still
// validates branch/doctor existence and double-booking either way.
function nowAsSlot(): TimeSlot {
  const now = new Date()
  return { minutesFromMidnight: now.getHours() * 60 + now.getMinutes(), label: now.toTimeString().slice(0, 5) }
}

export function AppointmentsPage() {
  const { doctors, isLoading: doctorsLoading } = useBookableDoctors()
  const { data: branches } = useBranches()
  const [doctorId, setDoctorId] = useState('')
  const [branchId, setBranchId] = useState('')
  const [dateValue, setDateValue] = useState(() => formatDateInput(new Date()))

  const [bookingSlot, setBookingSlot] = useState<TimeSlot | null>(null)
  const [reschedulingAppointment, setReschedulingAppointment] = useState<AppointmentSummary | null>(null)
  const [cancellingAppointmentId, setCancellingAppointmentId] = useState<string | null>(null)

  const selectedDoctor = doctors.find((d) => d.userId === doctorId)
  const selectedDate = useMemo(() => new Date(`${dateValue}T00:00:00`), [dateValue])

  // `items` is what makes each Select's closed trigger show a friendly
  // name instead of the raw UUID `value` — base-ui's Select.Value only
  // resolves a label from this map, never from the SelectItem children
  // rendered in the popup list. See issue-token-dialog.tsx's own note.
  const doctorSelectItems = useMemo(
    () => Object.fromEntries(doctors.map((d) => [d.userId, d.specialization ? `${d.name} — ${d.specialization}` : d.name])),
    [doctors],
  )
  const branchSelectItems = useMemo(() => Object.fromEntries((branches ?? []).map((b) => [b.id, b.name])), [branches])

  const dayHours = selectedDoctor ? dayHoursFor(selectedDoctor.workingHours, selectedDate) : null
  const slots = dayHours ? generateTimeSlots(dayHours.open, dayHours.close, SLOT_INCREMENT_MINUTES) : []

  const { data: appointmentsData, isLoading: appointmentsLoading } = useAppointmentSearch({
    doctorId: doctorId || undefined,
    dateFrom: startOfDay(selectedDate).toISOString(),
    dateTo: endOfDay(selectedDate).toISOString(),
    limit: 100,
  })
  const appointments = (appointmentsData?.items ?? []).filter((a) => a.status !== 'CANCELLED')

  const patientIds = useMemo(
    () => Array.from(new Set((appointmentsData?.items ?? []).filter((a) => a.status !== 'CANCELLED').map((a) => a.patient_id))),
    [appointmentsData?.items],
  )
  const patientQueries = useQueries({
    queries: patientIds.map((id) => ({ queryKey: ['patients', 'get', id], queryFn: () => getPatient(id), staleTime: 60_000 })),
  })
  const patientsById = useMemo(() => {
    const map = new Map<string, PatientSummary>()
    for (const q of patientQueries) if (q.data) map.set(q.data.id, q.data)
    return map
  }, [patientQueries])

  function appointmentForSlot(slot: TimeSlot): AppointmentSummary | undefined {
    const slotStart = slotToDate(selectedDate, slot.minutesFromMidnight).getTime()
    const slotEnd = slotStart + SLOT_INCREMENT_MINUTES * 60_000
    return appointments.find((a) => {
      const apptStart = new Date(a.scheduled_at).getTime()
      const apptEnd = apptStart + a.duration_minutes * 60_000
      return apptStart < slotEnd && apptEnd > slotStart
    })
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Appointments</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Book a slot against a doctor's working hours.</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Doctor</Label>
          <Select
            value={doctorId}
            onValueChange={(value) => {
              setDoctorId(value ?? '')
              const doc = doctors.find((d) => d.userId === value)
              setBranchId(doc?.branchIds[0] ?? '')
            }}
            items={doctorSelectItems}
          >
            <SelectTrigger className="w-full sm:w-56">
              <SelectValue placeholder={doctorsLoading ? 'Loading…' : 'Select doctor'} />
            </SelectTrigger>
            <SelectContent>
              {doctors.map((doc) => (
                <SelectItem key={doc.userId} value={doc.userId}>
                  {doc.name}
                  {doc.specialization ? ` — ${doc.specialization}` : ''}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {branches && branches.length > 1 && (
          <div className="flex flex-col gap-1.5">
            <Label>Branch</Label>
            <Select value={branchId} onValueChange={(value) => setBranchId(value ?? '')} items={branchSelectItems}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="Select branch" />
              </SelectTrigger>
              <SelectContent>
                {branches.map((branch) => (
                  <SelectItem key={branch.id} value={branch.id}>
                    {branch.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="apptPageDate">Date</Label>
          <Input id="apptPageDate" type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} className="w-full sm:w-40" />
        </div>

        {selectedDoctor && branchId && (
          <Button type="button" variant="outline" onClick={() => setBookingSlot(nowAsSlot())}>
            Book at a custom time
          </Button>
        )}
      </div>

      {!doctorId ? (
        <EmptyState icon={CalendarX2} title="Select a doctor" description="Choose a doctor and date to see their schedule." />
      ) : !selectedDoctor?.branchIds.length ? (
        <EmptyState
          icon={CalendarX2}
          title="No branch assigned"
          description="This doctor isn't assigned to any branch yet — assign one from Staff Directory before booking."
        />
      ) : !dayHours ? (
        <EmptyState
          icon={CalendarX2}
          title="Not available on this day"
          description="This doctor has no working hours configured for the selected date."
        />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y divide-slate-100 p-0 dark:divide-slate-800">
            {appointmentsLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 p-3">
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 flex-1" />
                </div>
              ))}

            {!appointmentsLoading &&
              slots.map((slot) => {
                const appointment = appointmentForSlot(slot)
                const patient = appointment ? patientsById.get(appointment.patient_id) : undefined
                const canManage = appointment && ACTIVE_APPOINTMENT_STATUSES.has(appointment.status)

                return (
                  <div key={slot.minutesFromMidnight} className="flex items-center justify-between gap-3 px-3 py-2.5">
                    <span className="w-14 shrink-0 font-mono text-sm text-slate-500 dark:text-slate-400">{slot.label}</span>
                    {!appointment ? (
                      <button
                        type="button"
                        className="flex-1 rounded-md border border-dashed border-slate-200 px-3 py-1.5 text-left text-sm text-slate-400 transition-colors hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 dark:border-slate-800 dark:hover:bg-indigo-500/10 dark:hover:text-indigo-400"
                        onClick={() => setBookingSlot(slot)}
                      >
                        Available — click to book
                      </button>
                    ) : (
                      <div className="flex flex-1 items-center justify-between gap-3">
                        <div className="flex flex-col">
                          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                            {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-4 w-24" />}
                          </span>
                          <span className="text-xs text-slate-500 dark:text-slate-400">{appointment.duration_minutes} min</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <StatusBadge status={appointment.status} />
                          {canManage && (
                            <>
                              <Button variant="ghost" size="sm" onClick={() => setReschedulingAppointment(appointment)}>
                                Reschedule
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-destructive"
                                onClick={() => setCancellingAppointmentId(appointment.id)}
                              >
                                Cancel
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
          </CardContent>
        </Card>
      )}

      {selectedDoctor && branchId && bookingSlot && (
        <BookAppointmentDialog
          doctorId={selectedDoctor.userId}
          branchId={branchId}
          initialDate={selectedDate}
          initialTime={bookingSlot.label}
          open={bookingSlot !== null}
          onOpenChange={(open) => !open && setBookingSlot(null)}
        />
      )}

      <RescheduleAppointmentDialog
        appointment={reschedulingAppointment}
        open={reschedulingAppointment !== null}
        onOpenChange={(open) => !open && setReschedulingAppointment(null)}
      />
      <CancelAppointmentDialog
        appointmentId={cancellingAppointmentId}
        open={cancellingAppointmentId !== null}
        onOpenChange={(open) => !open && setCancellingAppointmentId(null)}
      />
    </div>
  )
}
