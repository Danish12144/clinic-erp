import { ChevronLeft, Loader2, Search, UserRoundSearch } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useCreateAppointment } from '@/features/appointments/hooks'
import { usePatientSearch } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput } from '@/lib/working-hours'

const DURATION_OPTIONS = [15, 30, 45, 60]

export function BookAppointmentDialog({
  doctorId,
  branchId,
  initialDate,
  initialTime,
  open,
  onOpenChange,
}: {
  doctorId: string
  branchId: string
  initialDate: Date
  initialTime: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const [dateValue, setDateValue] = useState('')
  const [timeValue, setTimeValue] = useState('')
  const [duration, setDuration] = useState('15')
  const [notes, setNotes] = useState('')

  const { data: searchResults, isFetching } = usePatientSearch(searchTerm)
  const createAppointment = useCreateAppointment()

  useEffect(() => {
    if (open) {
      setSearchTerm('')
      setSelectedPatient(null)
      setDateValue(formatDateInput(initialDate))
      setTimeValue(initialTime)
      setDuration('15')
      setNotes('')
    }
  }, [open, initialDate, initialTime])

  async function handleBook() {
    if (!selectedPatient || !dateValue || !timeValue) return
    const scheduledAt = new Date(`${dateValue}T${timeValue}:00`)
    if (Number.isNaN(scheduledAt.getTime()) || scheduledAt <= new Date()) {
      toast.error('Pick a future date and time')
      return
    }
    try {
      const appointment = await createAppointment.mutateAsync({
        patient_id: selectedPatient.id,
        branch_id: branchId,
        doctor_id: doctorId,
        scheduled_at: scheduledAt.toISOString(),
        duration_minutes: Number(duration),
        notes: notes || undefined,
      })
      toast.success(`Appointment booked for ${new Date(appointment.scheduled_at).toLocaleString()}`)
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not book appointment', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Book appointment</DialogTitle>
          <DialogDescription>Confirm the patient, time, and duration.</DialogDescription>
        </DialogHeader>

        {!selectedPatient ? (
          <div className="flex flex-col gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
              <Input
                autoFocus
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Phone, MRN, or name…"
                className="pl-8"
              />
              {isFetching && (
                <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-slate-400" />
              )}
            </div>
            <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-800">
              {searchTerm.trim().length === 0 ? (
                <EmptyState icon={UserRoundSearch} title="Search for a patient" description="Type a phone number, MRN, or name to begin." />
              ) : !isFetching && searchResults?.items.length === 0 ? (
                <EmptyState icon={UserRoundSearch} title="No patients found" description="Try a different search term." />
              ) : (
                searchResults?.items.map((patient) => (
                  <button
                    key={patient.id}
                    type="button"
                    className="flex w-full flex-col gap-0.5 border-b border-slate-100 px-3 py-2 text-left last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                    onClick={() => setSelectedPatient(patient)}
                  >
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      MRN {patient.mrn} {patient.phone ? `· ${patient.phone}` : ''}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              className="flex w-fit items-center gap-1 text-xs text-slate-500 hover:text-slate-900 dark:hover:text-slate-100"
              onClick={() => setSelectedPatient(null)}
            >
              <ChevronLeft className="size-3.5" />
              Change patient
            </button>

            <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                {[selectedPatient.first_name, selectedPatient.last_name].filter(Boolean).join(' ')}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">MRN {selectedPatient.mrn}</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apptDate">Date</Label>
                <Input id="apptDate" type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="apptTime">Time</Label>
                <Input id="apptTime" type="time" value={timeValue} onChange={(e) => setTimeValue(e.target.value)} />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Duration</Label>
              <Select value={duration} onValueChange={(v) => setDuration(v ?? '15')}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DURATION_OPTIONS.map((d) => (
                    <SelectItem key={d} value={String(d)}>
                      {d} minutes
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="apptNotes">Notes (optional)</Label>
              <Textarea id="apptNotes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={createAppointment.isPending} onClick={() => void handleBook()}>
                {createAppointment.isPending ? 'Booking…' : 'Book appointment'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
