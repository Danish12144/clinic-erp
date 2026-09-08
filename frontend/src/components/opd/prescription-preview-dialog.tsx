import { Download, Loader2, Printer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { downloadDocumentBlob } from '@/features/files/api'
import { getErrorMessage } from '@/lib/errors'

export function PrescriptionPreviewDialog({
  documentId,
  open,
  onOpenChange,
}: {
  documentId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    if (!open || !documentId) return
    let cancelled = false
    let objectUrl: string | null = null

    setLoading(true)
    setError(null)
    downloadDocumentBlob(documentId)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setBlobUrl(objectUrl)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load the prescription PDF.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setBlobUrl(null)
    }
  }, [open, documentId])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] max-w-3xl flex-col">
        <DialogHeader>
          <DialogTitle>Prescription generated</DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-muted/30">
          {loading && (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="size-6 animate-spin" />
            </div>
          )}
          {error && <p className="p-4 text-sm text-destructive">{error}</p>}
          {blobUrl && !loading && (
            <iframe ref={iframeRef} src={blobUrl} title="Prescription PDF" className="size-full" />
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            className="gap-1.5"
            disabled={!blobUrl}
            onClick={() => {
              if (!blobUrl) return
              const link = document.createElement('a')
              link.href = blobUrl
              link.download = 'prescription.pdf'
              link.click()
            }}
          >
            <Download className="size-4" />
            Download
          </Button>
          <Button
            className="gap-1.5"
            disabled={!blobUrl}
            onClick={() => iframeRef.current?.contentWindow?.print()}
          >
            <Printer className="size-4" />
            Print
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
