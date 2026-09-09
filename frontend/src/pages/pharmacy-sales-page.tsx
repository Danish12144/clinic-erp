import { Receipt } from 'lucide-react'
import { OtcCheckoutCard } from '@/components/pharmacy/otc-checkout-card'
import { PharmacyTabs } from '@/components/pharmacy/pharmacy-tabs'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useOtcSales } from '@/features/pharmacy/hooks'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function PharmacySalesPage() {
  const { data, isLoading, isError } = useOtcSales({ limit: 20 })

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Pharmacy</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Over-the-counter sales.</p>
      </div>

      <PharmacyTabs />

      {isError ? (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
          OTC sales aren't enabled for this clinic yet. Ask your Owner to turn on <code>features.pharmacy_enabled</code> in
          clinic settings.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OtcCheckoutCard />

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent sales</CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="flex flex-col gap-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : !data || data.items.length === 0 ? (
                <EmptyState icon={Receipt} title="No sales yet" description="Completed OTC sales will show up here." />
              ) : (
                <>
                  <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
                    {data.items.map((sale) => (
                      <li key={sale.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                        <div className="flex flex-col">
                          <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                            {sale.customer_name ?? 'Walk-in customer'}
                          </span>
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {sale.items.length} item{sale.items.length === 1 ? '' : 's'} ·{' '}
                            {new Date(sale.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Badge variant={sale.status === 'REFUNDED' ? 'destructive' : 'secondary'}>{sale.status}</Badge>
                          <span className="font-medium text-slate-900 dark:text-slate-100">{formatMoney(sale.net_amount)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-3 flex justify-between border-t border-slate-200 pt-2 text-sm dark:border-slate-800">
                    <span className="text-slate-500 dark:text-slate-400">Total (filtered)</span>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{formatMoney(data.total_net_amount)}</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
