import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useRescheduleMyAppointment } from '@/features/appointments/hooks'
import type { AppointmentSummary } from '@/features/appointments/types'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput, isSchedulableMoment } from '@/lib/working-hours'

export function RescheduleMyAppointmentDialog({
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
  const rescheduleMyAppointment = useRescheduleMyAppointment()

  useEffect(() => {
    if (open && appointment) {
      const current = new Date(appointment.scheduled_at)
      setDateValue(formatDateInput(current))
      setTimeValue(`${String(current.getHours()).padStart(2, '0')}:${String(current.getMinutes()).padStart(2, '0')}`)
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
      await rescheduleMyAppointment.mutateAsync({
        appointmentId: appointment.id,
        payload: { scheduled_at: scheduledAt.toISOString() },
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
            <Label htmlFor="myReschedDate">Date</Label>
            <Input id="myReschedDate" type="date" value={dateValue} onChange={(e) => setDateValue(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="myReschedTime">Time</Label>
            <Input id="myReschedTime" type="time" value={timeValue} onChange={(e) => setTimeValue(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button disabled={rescheduleMyAppointment.isPending} onClick={() => void handleReschedule()}>
            {rescheduleMyAppointment.isPending ? 'Saving…' : 'Save new time'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
