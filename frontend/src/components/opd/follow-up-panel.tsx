import { CalendarClock } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/auth-context'
import { useCreateFollowUp } from '@/features/followups/hooks'
import { getErrorMessage } from '@/lib/errors'

export function FollowUpPanel({ patientId, encounterId }: { patientId: string; encounterId: string }) {
  const { hasPermission } = useAuth()
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [scheduled, setScheduled] = useState<string | null>(null)
  const createFollowUp = useCreateFollowUp()

  if (!hasPermission('crm.manage')) return null

  async function onSchedule() {
    if (!date) {
      toast.error('Pick a follow-up date')
      return
    }
    try {
      const dueAt = new Date(`${date}T09:00:00`).toISOString()
      await createFollowUp.mutateAsync({ patient_id: patientId, encounter_id: encounterId, due_at: dueAt, reason: reason || undefined })
      setScheduled(date)
      toast.success('Follow-up scheduled')
    } catch (error) {
      toast.error('Could not schedule follow-up', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5 text-base">
          <CalendarClock className="size-4" />
          Follow-up (optional)
        </CardTitle>
      </CardHeader>
      <CardContent>
        {scheduled ? (
          <p className="text-sm text-muted-foreground">
            Follow-up scheduled for <span className="font-medium text-foreground">{scheduled}</span>.
          </p>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="followup-date">Date</Label>
              <Input id="followup-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </div>
            <div className="flex flex-1 min-w-40 flex-col gap-1.5">
              <Label htmlFor="followup-reason">Reason</Label>
              <Input
                id="followup-reason"
                placeholder="e.g. suture removal"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            <Button type="button" size="sm" disabled={createFollowUp.isPending} onClick={() => void onSchedule()}>
              {createFollowUp.isPending ? 'Scheduling…' : 'Schedule'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
