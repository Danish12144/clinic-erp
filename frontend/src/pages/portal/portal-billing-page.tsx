import { ChevronDown, ChevronUp, Receipt } from 'lucide-react'
import { useState } from 'react'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useMyInvoices } from '@/features/billing/hooks'
import type { InvoiceSummary } from '@/features/billing/types'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function InvoiceCard({ invoice }: { invoice: InvoiceSummary }) {
  const [expanded, setExpanded] = useState(false)
  const balanceDue = Number(invoice.balance_due)

  return (
    <Card size="sm">
      <CardContent className="flex flex-col gap-2">
        <button type="button" className="flex w-full items-center justify-between gap-3 text-left" onClick={() => setExpanded((v) => !v)}>
          <div>
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{new Date(invoice.created_at).toLocaleDateString()}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {formatMoney(invoice.total)}
              {balanceDue > 0 && invoice.status !== 'VOID' && (
                <span className="text-amber-600 dark:text-amber-400"> · {formatMoney(invoice.balance_due)} due</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={invoice.status} />
            {expanded ? <ChevronUp className="size-4 text-slate-400" /> : <ChevronDown className="size-4 text-slate-400" />}
          </div>
        </button>

        {expanded && (
          <div className="flex flex-col gap-3 border-t border-slate-200 pt-3 dark:border-slate-800">
            <div className="flex flex-col gap-1">
              {invoice.line_items.map((item) => (
                <div key={item.id} className="flex items-center justify-between text-sm">
                  <span className="text-slate-600 dark:text-slate-400">
                    {item.description} {Number(item.quantity) !== 1 ? `× ${item.quantity}` : ''}
                  </span>
                  <span className="text-slate-900 dark:text-slate-100">{formatMoney(item.total)}</span>
                </div>
              ))}
              {(Number(invoice.tax) > 0 || Number(invoice.discount) > 0) && (
                <>
                  {Number(invoice.tax) > 0 && (
                    <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
                      <span>Tax</span>
                      <span>{formatMoney(invoice.tax)}</span>
                    </div>
                  )}
                  {Number(invoice.discount) > 0 && (
                    <div className="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
                      <span>Discount</span>
                      <span>-{formatMoney(invoice.discount)}</span>
                    </div>
                  )}
                </>
              )}
              <div className="flex items-center justify-between border-t border-slate-100 pt-1 text-sm font-medium text-slate-900 dark:border-slate-800 dark:text-slate-100">
                <span>Total</span>
                <span>{formatMoney(invoice.total)}</span>
              </div>
            </div>

            {invoice.payments.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Payments</p>
                {invoice.payments.map((payment) => (
                  <div key={payment.id} className="flex items-center justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-400">
                      {new Date(payment.recorded_at).toLocaleDateString()} · {payment.method}
                    </span>
                    <span className={Number(payment.amount) < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-slate-900 dark:text-slate-100'}>
                      {formatMoney(payment.amount)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function PortalBillingPage() {
  const { data, isLoading } = useMyInvoices()
  const invoices = data?.items ?? []

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Billing</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Your invoices and payment history.</p>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : invoices.length === 0 ? (
        <EmptyState icon={Receipt} title="No invoices yet" description="Invoices from your visits will appear here." />
      ) : (
        <div className="flex flex-col gap-2">
          {invoices.map((invoice) => (
            <InvoiceCard key={invoice.id} invoice={invoice} />
          ))}
        </div>
      )}
    </div>
  )
}
