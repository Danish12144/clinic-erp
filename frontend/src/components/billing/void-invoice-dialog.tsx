import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useVoidInvoice } from '@/features/billing/hooks'
import { getErrorMessage } from '@/lib/errors'

export function VoidInvoiceDialog({
  invoiceId,
  hasPayments,
  open,
  onOpenChange,
}: {
  invoiceId: string
  hasPayments: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [reason, setReason] = useState('')
  const voidInvoice = useVoidInvoice(invoiceId)

  async function handleVoid() {
    if (!reason.trim()) {
      toast.error('Enter a reason')
      return
    }
    try {
      await voidInvoice.mutateAsync({ reason })
      toast.success('Invoice voided')
      setReason('')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not void invoice', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Void invoice</DialogTitle>
          <DialogDescription>
            {hasPayments
              ? 'This invoice has recorded payments — voiding it will auto-create a reversing refund entry.'
              : 'This cannot be undone. The invoice stays visible for audit history.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="void-reason">Reason</Label>
          <Textarea id="void-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" disabled={voidInvoice.isPending} onClick={() => void handleVoid()}>
            {voidInvoice.isPending ? 'Voiding…' : 'Void invoice'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
