import { FlaskConical } from 'lucide-react'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useLabOrders } from '@/features/lab/hooks'

export function PortalLabResultsPage() {
  // No params — the backend auto-scopes a PATIENT caller to their own
  // record and hard-filters to COMPLETED orders only (LabOrderService.
  // search_orders), the same "reads completed reports, not pending ones"
  // rule the rest of the app already relies on. retry:false (baked into
  // useLabOrders) means a 403 here (most likely: features.lab_enabled is
  // off for this clinic) surfaces once as isError rather than retry-storming.
  const { data, isLoading, isError } = useLabOrders({})
  const orders = data?.items ?? []

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Lab results</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Completed reports from your visits.</p>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : isError ? (
        <EmptyState icon={FlaskConical} title="Lab results aren't available" description="This clinic hasn't enabled lab reporting yet." />
      ) : orders.length === 0 ? (
        <EmptyState icon={FlaskConical} title="No completed lab results yet" description="Reports appear here once a lab order is finalized." />
      ) : (
        <div className="flex flex-col gap-3">
          {orders.map((order) => (
            <Card key={order.id} size="sm">
              <CardContent className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{order.test.name}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {order.completed_at ? new Date(order.completed_at).toLocaleDateString() : new Date(order.ordered_at).toLocaleDateString()}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </div>

                {order.results.length > 0 && (
                  <div className="flex flex-col gap-1 border-t border-slate-200 pt-2 dark:border-slate-800">
                    {order.results.map((result) => (
                      <div key={result.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="text-slate-600 dark:text-slate-400">{result.parameter}</span>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-slate-900 dark:text-slate-100">
                            {result.value}
                            {result.unit ? ` ${result.unit}` : ''}
                          </span>
                          {result.reference_range && (
                            <span className="text-xs text-slate-400 dark:text-slate-600">({result.reference_range})</span>
                          )}
                          <StatusBadge status={result.flag} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
