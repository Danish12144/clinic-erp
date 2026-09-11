import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { VitalsPanel } from '@/components/opd/vitals-panel'

// A thin Dialog wrapper around the existing VitalsPanel (built for the
// Doctor's consultation pad) — reused as-is, zero duplication, for the
// one thing a Nurse can actually do from the OPD queue: record a vitals
// reading against a patient's OPEN/IN_CONSULTATION encounter without
// needing consultation.manage (the full clinical pad stays doctor/owner-
// only). See OpdQueuePage's own comment for why this exists at all —
// Nurse held vitals.record on the backend since migration 0001 but had
// no frontend entry point to actually use it.
export function RecordVitalsDialog({
  encounterId,
  open,
  onOpenChange,
}: {
  encounterId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Record vitals</DialogTitle>
        </DialogHeader>
        {encounterId && <VitalsPanel encounterId={encounterId} />}
      </DialogContent>
    </Dialog>
  )
}
