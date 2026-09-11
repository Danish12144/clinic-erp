import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useRescheduleAppointment } from '@/features/appointments/hooks'
import type { AppointmentSummary } from '@/features/appointments/types'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput, isSchedulableMoment } from '@/lib/working-hours'

const DURATION_OPTIONS = [15, 30, 45, 60]

export function RescheduleAppointmentDialog({
  appointment,
  open,
  onOpenChange,
}: {
  appointment: AppointmentSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [dateValue, setDateValue] = useState('')
  const [timeValue, setTimeValue] = useState('')
  const [duration, setDuration] = useState('15')
  const rescheduleAppointment = useRescheduleAppointment()

  useEffect(() => {
    if (open && appointment) {
      const current = new Date(appointment.scheduled_at)
      setDateValue(formatDateInput(current))
      setTimeValue(`${String(current.getHours()).padStart(2, '0')}:${String(current.getMinutes()).padStart(2, '0')}`)
      setDuration(String(appointment.duration_minutes))
    }
  }, [open, appointment])

  async function handleReschedule() {
    if (!appointment || !dateValue || !timeValue) return
    const scheduledAt = new Date(`${dateValue}T${timeValue}:00`)
    if (Number.isNaN(scheduledAt.getTime()) || !isSchedulableMoment(scheduledAt)) {
      toast.error('Pick a future date and time')
      return
    }
    try {
      await rescheduleAppointment.mutateAsync({
        appointmentId: appointment.id,
        payload: { scheduled_at: scheduledAt.toISOString(), duration_minutes: Number(duration) },
      })
      toast.success('Appointment rescheduled')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not reschedule appointment', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Reschedule appointment</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reschedDate">Date</Label>
            <Input id="reschedDate" type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reschedTime">Time</Label>
            <Input id="reschedTime" type="time" value={timeValue} onChange={(e) => setTimeValue(e.target.value)} />
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
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={rescheduleAppointment.isPending} onClick={() => void handleReschedule()}>
            {rescheduleAppointment.isPending ? 'Saving…' : 'Save new time'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
