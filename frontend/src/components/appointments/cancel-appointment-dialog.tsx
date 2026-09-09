import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useCancelAppointment } from '@/features/appointments/hooks'
import { getErrorMessage } from '@/lib/errors'

export function CancelAppointmentDialog({
  appointmentId,
  open,
  onOpenChange,
}: {
  appointmentId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [reason, setReason] = useState('')
  const cancelAppointment = useCancelAppointment()

  async function handleCancel() {
    if (!appointmentId) return
    if (!reason.trim()) {
      toast.error('Enter a reason')
      return
    }
    try {
      await cancelAppointment.mutateAsync({ appointmentId, payload: { reason } })
      toast.success('Appointment cancelled')
      setReason('')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not cancel appointment', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Cancel appointment</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cancel-appt-reason">Reason</Label>
          <Textarea id="cancel-appt-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button variant="destructive" disabled={cancelAppointment.isPending} onClick={() => void handleCancel()}>
            {cancelAppointment.isPending ? 'Cancelling…' : 'Cancel appointment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
