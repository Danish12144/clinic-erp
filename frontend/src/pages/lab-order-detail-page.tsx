import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowLeft, Ban, CheckCircle2, FlaskConical, Plus, TestTube2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { Link, Navigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/features/auth/auth-context'
import { useCancelLabOrder, useCollectSample, useCompleteLabOrder, useAddLabResults, useLabOrder } from '@/features/lab/hooks'
import { usePatient } from '@/features/patients/hooks'
import { getErrorMessage } from '@/lib/errors'

const FLAG_OVERRIDES = ['', 'NORMAL', 'LOW', 'HIGH', 'CRITICAL'] as const

const resultRowSchema = z.object({
  parameter: z.string().min(1, 'Required').max(300),
  value: z.string().min(1, 'Required').max(500),
  unit: z.string().max(50).optional().or(z.literal('')),
  flagOverride: z.enum(FLAG_OVERRIDES).optional(),
})

const resultsFormSchema = z.object({ results: z.array(resultRowSchema).min(1) })
type ResultsFormValues = z.infer<typeof resultsFormSchema>

const EMPTY_RESULT_ROW = { parameter: '', value: '', unit: '', flagOverride: '' as const }

function ResultEntryForm({ orderId }: { orderId: string }) {
  const addResults = useAddLabResults(orderId)
  const { control, register, handleSubmit, reset } = useForm<ResultsFormValues>({
    resolver: zodResolver(resultsFormSchema),
    defaultValues: { results: [{ ...EMPTY_RESULT_ROW }] },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'results' })

  async function onSubmit(values: ResultsFormValues) {
    try {
      await addResults.mutateAsync({
        results: values.results.map((r) => ({
          parameter: r.parameter,
          value: r.value,
          unit: r.unit || undefined,
          flag_override: r.flagOverride || undefined,
        })),
      })
      toast.success('Results recorded')
      // Additive endpoint (each call adds new rows) — reset to a single
      // blank row so Lab Staff can keep entering the next parameter/batch
      // without re-typing over what they just saved.
      reset({ results: [{ ...EMPTY_RESULT_ROW }] })
    } catch (error) {
      toast.error('Could not record results', { description: getErrorMessage(error) })
    }
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
      {fields.map((field, index) => (
        <div key={field.id} className="grid grid-cols-1 gap-2 rounded-md border border-slate-200 p-3 sm:grid-cols-5 dark:border-slate-800">
          <div className="flex flex-col gap-1 sm:col-span-2">
            <Label className="text-xs">Parameter</Label>
            <Input {...register(`results.${index}.parameter`)} placeholder="Hemoglobin" />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Value</Label>
            <Input {...register(`results.${index}.value`)} placeholder="13.5" />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Unit</Label>
            <Input {...register(`results.${index}.unit`)} placeholder="g/dL" />
          </div>
          <div className="flex items-end gap-1">
            <div className="flex flex-1 flex-col gap-1">
              <Label className="text-xs">Flag override</Label>
              <Controller
                control={control}
                name={`results.${index}.flagOverride`}
                render={({ field: f }) => (
                  <Select value={f.value ?? ''} onValueChange={(v) => f.onChange(v ?? '')}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Auto" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">Auto</SelectItem>
                      <SelectItem value="NORMAL">Normal</SelectItem>
                      <SelectItem value="LOW">Low</SelectItem>
                      <SelectItem value="HIGH">High</SelectItem>
                      <SelectItem value="CRITICAL">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <Button type="button" variant="ghost" size="icon-sm" disabled={fields.length === 1} onClick={() => remove(index)}>
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => append({ ...EMPTY_RESULT_ROW })}>
          <Plus className="size-3.5" />
          Add parameter
        </Button>
        <Button type="submit" disabled={addResults.isPending}>
          {addResults.isPending ? 'Saving…' : 'Save results'}
        </Button>
      </div>
    </form>
  )
}

function CancelOrderDialog({ orderId, open, onOpenChange }: { orderId: string; open: boolean; onOpenChange: (open: boolean) => void }) {
  const [reason, setReason] = useState('')
  const cancelOrder = useCancelLabOrder(orderId)

  async function handleCancel() {
    if (!reason.trim()) {
      toast.error('Enter a reason')
      return
    }
    try {
      await cancelOrder.mutateAsync({ reason })
      toast.success('Order cancelled')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not cancel order', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Cancel lab order</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cancel-reason">Reason</Label>
          <Textarea id="cancel-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Back
          </Button>
          <Button variant="destructive" disabled={cancelOrder.isPending} onClick={() => void handleCancel()}>
            {cancelOrder.isPending ? 'Cancelling…' : 'Cancel order'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function LabOrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>()
  const { hasPermission } = useAuth()
  const { data: order, isLoading } = useLabOrder(orderId)
  const { data: patient } = usePatient(order?.patient_id)
  const collectSample = useCollectSample(orderId ?? '')
  const completeOrder = useCompleteLabOrder(orderId ?? '')
  const [cancelOpen, setCancelOpen] = useState(false)

  if (!orderId) return <Navigate to="/lab" replace />

  const canEnterResults = hasPermission('lab.enter_results')
  const canOrder = hasPermission('lab.order')

  if (isLoading || !order) {
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  const isTerminal = order.status === 'COMPLETED' || order.status === 'CANCELLED'
  const canCollectSample = canEnterResults && order.status === 'ORDERED'
  const canEnterMoreResults = canEnterResults && (order.status === 'SAMPLE_COLLECTED' || order.status === 'RESULTED')
  const canComplete = canEnterResults && order.status === 'RESULTED'
  const canCancel = canOrder && !isTerminal

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/lab" className="mb-1 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 dark:hover:text-slate-100">
            <ArrowLeft className="size-3.5" />
            Back to lab orders
          </Link>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">{order.test.name}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-4 w-32" />}
            {patient && ` · MRN ${patient.mrn}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={order.status} />
          {canCollectSample && (
            <Button
              size="sm"
              className="gap-1.5"
              disabled={collectSample.isPending}
              onClick={async () => {
                try {
                  await collectSample.mutateAsync()
                  toast.success('Sample marked as collected')
                } catch (error) {
                  toast.error('Could not collect sample', { description: getErrorMessage(error) })
                }
              }}
            >
              <TestTube2 className="size-3.5" />
              {collectSample.isPending ? 'Collecting…' : 'Collect sample'}
            </Button>
          )}
          {canComplete && (
            <Button
              size="sm"
              className="gap-1.5"
              disabled={completeOrder.isPending}
              onClick={async () => {
                try {
                  await completeOrder.mutateAsync()
                  toast.success('Order completed — report finalized')
                } catch (error) {
                  toast.error('Could not complete order', { description: getErrorMessage(error) })
                }
              }}
            >
              <CheckCircle2 className="size-3.5" />
              {completeOrder.isPending ? 'Completing…' : 'Complete & finalize'}
            </Button>
          )}
          {canCancel && (
            <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => setCancelOpen(true)}>
              <Ban className="size-3.5" />
              Cancel
            </Button>
          )}
        </div>
      </div>

      {order.cancelled_reason && (
        <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-700 dark:bg-rose-500/15 dark:text-rose-400">
          Cancelled: {order.cancelled_reason}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Results</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {order.results.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No results recorded yet.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
              {order.results.map((result) => (
                <li key={result.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                  <div className="flex flex-col">
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{result.parameter}</span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      {result.value} {result.unit ?? ''} {result.reference_range ? `(ref: ${result.reference_range})` : ''}
                    </span>
                  </div>
                  <StatusBadge status={result.flag} />
                </li>
              ))}
            </ul>
          )}

          {canEnterMoreResults && (
            <>
              <div className="border-t border-slate-200 dark:border-slate-800" />
              <ResultEntryForm orderId={orderId} />
            </>
          )}

          {!canEnterResults && order.results.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-8 text-center">
              <FlaskConical className="size-8 text-slate-300" />
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Waiting on {order.status === 'ORDERED' ? 'sample collection' : 'results'}.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <CancelOrderDialog orderId={orderId} open={cancelOpen} onOpenChange={setCancelOpen} />
    </div>
  )
}
