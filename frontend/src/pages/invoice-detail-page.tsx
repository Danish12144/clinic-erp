import { ArrowLeft, Ban, Plus, Receipt, Send, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Link, Navigate, useParams } from 'react-router-dom'
import { AddLineItemDialog } from '@/components/billing/add-line-item-dialog'
import { RecordPaymentDialog } from '@/components/billing/record-payment-dialog'
import { VoidInvoiceDialog } from '@/components/billing/void-invoice-dialog'
import { StatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useDeleteLineItem, useInvoice, useIssueInvoice } from '@/features/billing/hooks'
import { usePatient } from '@/features/patients/hooks'
import { getErrorMessage } from '@/lib/errors'

const SOURCE_LABELS: Record<string, string> = {
  CONSULTATION: 'Consultation',
  PROCEDURE: 'Procedure',
  PHARMACY: 'Pharmacy',
  LAB: 'Lab',
  OTHER: 'Other',
}

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function InvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>()
  const { hasPermission } = useAuth()
  const { data: invoice, isLoading } = useInvoice(invoiceId)
  const { data: patient } = usePatient(invoice?.patient_id)
  const issueInvoice = useIssueInvoice(invoiceId ?? '')
  const deleteLineItem = useDeleteLineItem(invoiceId ?? '')

  const [addItemOpen, setAddItemOpen] = useState(false)
  const [paymentOpen, setPaymentOpen] = useState(false)
  const [voidOpen, setVoidOpen] = useState(false)

  if (!invoiceId) return <Navigate to="/billing" replace />

  const canManage = hasPermission('billing.manage')
  const canRecordPayment = hasPermission('payments.record')
  const isDraft = invoice?.status === 'DRAFT'
  const isVoid = invoice?.status === 'VOID'

  if (isLoading || !invoice) {
    return (
      <div className="flex flex-col gap-4 p-4 sm:p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/billing" className="mb-1 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900 dark:hover:text-slate-100">
            <ArrowLeft className="size-3.5" />
            Back to billing
          </Link>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
            {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-6 w-40" />}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">{patient ? `MRN ${patient.mrn}` : ''}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="secondary">{SOURCE_LABELS[invoice.source_type] ?? invoice.source_type}</Badge>
          <StatusBadge status={invoice.status} />
          {!isDraft && !isVoid && <StatusBadge status={invoice.payment_status} />}
          {canManage && isDraft && (
            <Button
              size="sm"
              className="gap-1.5"
              disabled={issueInvoice.isPending || invoice.line_items.length === 0}
              onClick={async () => {
                try {
                  await issueInvoice.mutateAsync()
                  toast.success('Invoice issued')
                } catch (error) {
                  toast.error('Could not issue invoice', { description: getErrorMessage(error) })
                }
              }}
            >
              <Send className="size-3.5" />
              {issueInvoice.isPending ? 'Issuing…' : 'Issue invoice'}
            </Button>
          )}
          {canRecordPayment && !isDraft && !isVoid && (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setPaymentOpen(true)}>
              <Receipt className="size-3.5" />
              Record payment
            </Button>
          )}
          {canManage && !isVoid && (
            <Button size="sm" variant="destructive" className="gap-1.5" onClick={() => setVoidOpen(true)}>
              <Ban className="size-3.5" />
              Void
            </Button>
          )}
        </div>
      </div>

      {isDraft && invoice.line_items.length === 0 && (
        <p className="rounded-md bg-amber-50 p-2 text-sm text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
          Add at least one line item before issuing this invoice.
        </p>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-base">Line items</CardTitle>
          {canManage && isDraft && (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setAddItemOpen(true)}>
              <Plus className="size-3.5" />
              Add item
            </Button>
          )}
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit price</TableHead>
                <TableHead className="text-right">Total</TableHead>
                {canManage && isDraft && <TableHead className="w-10" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoice.line_items.length === 0 && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={6} className="py-6 text-center text-sm text-slate-500">
                    No line items yet.
                  </TableCell>
                </TableRow>
              )}
              {invoice.line_items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <Badge variant="secondary">{SOURCE_LABELS[item.source_type] ?? item.source_type}</Badge>
                  </TableCell>
                  <TableCell className="text-slate-700 dark:text-slate-300">{item.description}</TableCell>
                  <TableCell className="text-right text-slate-700 dark:text-slate-300">{item.quantity}</TableCell>
                  <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(item.unit_price)}</TableCell>
                  <TableCell className="text-right font-medium text-slate-900 dark:text-slate-100">{formatMoney(item.total)}</TableCell>
                  {canManage && isDraft && (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={async () => {
                          try {
                            await deleteLineItem.mutateAsync(item.id)
                          } catch (error) {
                            toast.error('Could not remove item', { description: getErrorMessage(error) })
                          }
                        }}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Summary</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Subtotal</span>
              <span className="text-slate-900 dark:text-slate-100">{formatMoney(invoice.subtotal)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Tax</span>
              <span className="text-slate-900 dark:text-slate-100">{formatMoney(invoice.tax)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Discount</span>
              <span className="text-slate-900 dark:text-slate-100">-{formatMoney(invoice.discount)}</span>
            </div>
            <div className="mt-1 flex justify-between border-t border-slate-200 pt-1.5 font-medium dark:border-slate-800">
              <span className="text-slate-900 dark:text-slate-100">Total</span>
              <span className="text-slate-900 dark:text-slate-100">{formatMoney(invoice.total)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Paid</span>
              <span className="text-emerald-600 dark:text-emerald-400">{formatMoney(invoice.total_paid)}</span>
            </div>
            <div className="flex justify-between font-medium">
              <span className="text-slate-900 dark:text-slate-100">Balance due</span>
              <span className="text-slate-900 dark:text-slate-100">{formatMoney(invoice.balance_due)}</span>
            </div>
            {invoice.voided_reason && (
              <p className="mt-2 rounded-md bg-rose-50 p-2 text-xs text-rose-700 dark:bg-rose-500/15 dark:text-rose-400">
                Voided: {invoice.voided_reason}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payments</CardTitle>
          </CardHeader>
          <CardContent>
            {invoice.payments.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No payments recorded yet.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
                {invoice.payments.map((payment) => {
                  const isRefund = Number(payment.amount) < 0
                  return (
                    <li key={payment.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                      <div className="flex flex-col">
                        <span className={`text-sm font-medium ${isRefund ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-slate-100'}`}>
                          {isRefund ? '-' : ''}
                          {formatMoney(String(Math.abs(Number(payment.amount))))}
                        </span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {payment.method} · {new Date(payment.recorded_at).toLocaleString()}
                          {payment.recorded_by_name && <> · Received by {payment.recorded_by_name}</>}
                        </span>
                      </div>
                      {isRefund && <Badge variant="outline">Refund</Badge>}
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <AddLineItemDialog invoiceId={invoiceId} open={addItemOpen} onOpenChange={setAddItemOpen} />
      <RecordPaymentDialog invoiceId={invoiceId} balanceDue={invoice.balance_due} open={paymentOpen} onOpenChange={setPaymentOpen} />
      <VoidInvoiceDialog invoiceId={invoiceId} hasPayments={invoice.payments.length > 0} open={voidOpen} onOpenChange={setVoidOpen} />
    </div>
  )
}
