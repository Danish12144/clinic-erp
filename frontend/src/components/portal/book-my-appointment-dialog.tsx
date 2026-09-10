import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useBranches } from '@/features/branches/hooks'
import { useCreateMyAppointment } from '@/features/appointments/hooks'
import { useBookableDoctors } from '@/features/doctors/hooks'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput } from '@/lib/working-hours'

const DURATION_OPTIONS = [15, 30, 45, 60]

export function BookMyAppointmentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { data: branches } = useBranches()
  const { doctors, isLoading: doctorsLoading } = useBookableDoctors()
  const createMyAppointment = useCreateMyAppointment()

  const [branchId, setBranchId] = useState('')
  const [doctorId, setDoctorId] = useState('')
  const [dateValue, setDateValue] = useState('')
  const [timeValue, setTimeValue] = useState('')
  const [duration, setDuration] = useState('15')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (open) {
      setBranchId(branches?.[0]?.id ?? '')
      setDoctorId('')
      setDateValue(formatDateInput(new Date()))
      setTimeValue('')
      setDuration('15')
      setNotes('')
    }
  }, [open, branches])

  async function handleBook() {
    if (!branchId || !doctorId || !dateValue || !timeValue) {
      toast.error('Pick a doctor, date, and time')
      return
    }
    const scheduledAt = new Date(`${dateValue}T${timeValue}:00`)
    if (Number.isNaN(scheduledAt.getTime()) || scheduledAt <= new Date()) {
      toast.error('Pick a future date and time')
      return
    }
    try {
      const appointment = await createMyAppointment.mutateAsync({
        branch_id: branchId,
        doctor_id: doctorId,
        scheduled_at: scheduledAt.toISOString(),
        duration_minutes: Number(duration),
        notes: notes || undefined,
      })
      toast.success(`Appointment booked for ${new Date(appointment.scheduled_at).toLocaleString()}`)
      onOpenChange(false)
    } catch (error) {
      // A 422 here is almost always "outside this doctor's working hours"
      // or "conflicts with an existing appointment" — AppointmentService.
      // _validate_slot is the single source of truth, there's no separate
      // slots API this dialog can check ahead of time, so the backend's
      // own message is what the patient sees.
      toast.error('Could not book appointment', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Book an appointment</DialogTitle>
          <DialogDescription>Pick a doctor and a time that works for you.</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {branches && branches.length > 1 && (
            <div className="flex flex-col gap-1.5">
              <Label>Branch</Label>
              <Select value={branchId} onValueChange={(value) => value && setBranchId(value)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
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
            <Label>Doctor</Label>
            <Select value={doctorId} onValueChange={(value) => value && setDoctorId(value)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder={doctorsLoading ? 'Loading doctors…' : 'Choose a doctor'} />
              </SelectTrigger>
              <SelectContent>
                {doctors.map((doctor) => (
                  <SelectItem key={doctor.userId} value={doctor.userId}>
                    {doctor.name}
                    {doctor.specialization ? ` — ${doctor.specialization}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!doctorsLoading && doctors.length === 0 && (
              <p className="text-xs text-slate-500 dark:text-slate-400">No doctors are available to book right now.</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="myApptDate">Date</Label>
              <Input id="myApptDate" type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="myApptTime">Time</Label>
              <Input id="myApptTime" type="time" value={timeValue} onChange={(e) => setTimeValue(e.target.value)} />
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
            <Label htmlFor="myApptNotes">Reason for visit (optional)</Label>
            <Textarea id="myApptNotes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" disabled={createMyAppointment.isPending} onClick={() => void handleBook()}>
            {createMyAppointment.isPending ? 'Booking…' : 'Book appointment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
