import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/features/auth/auth-context'
import { useCreateLabOrder, useEncounterLabOrders, useLabTestSearch } from '@/features/lab/hooks'
import { getErrorMessage } from '@/lib/errors'

// Renders nothing at all when the Lab module isn't reachable for this
// caller/clinic (feature flag off, or no lab.order permission) — a
// deliberate, quiet degrade, same reasoning as the doctor-directory picker
// hiding for Owner in the Patients module: an absent capability isn't an
// error state to surface, it's just not part of this clinic's setup.
export function LabOrderPanel({ encounterId }: { encounterId: string }) {
  const { hasPermission } = useAuth()
  const [query, setQuery] = useState('')
  const { data: testResults, isFetching } = useLabTestSearch(query)
  const ordersQuery = useEncounterLabOrders(encounterId)
  const createOrder = useCreateLabOrder()

  if (!hasPermission('lab.order')) return null

  async function orderTest(testId: string, testName: string) {
    try {
      await createOrder.mutateAsync({ encounter_id: encounterId, test_id: testId })
      toast.success(`Ordered: ${testName}`)
      setQuery('')
    } catch (error) {
      toast.error('Could not order test', { description: getErrorMessage(error) })
    }
  }

  // A 403 here (most likely: features.lab_enabled is off for this clinic)
  // means the whole section quietly disappears rather than showing an
  // error for an optional module the clinic never turned on. Wait for the
  // first result before deciding, so the section doesn't flash and vanish.
  if (ordersQuery.isLoading || ordersQuery.isError) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5 text-base">
          <FlaskConical className="size-4" />
          Lab tests (optional)
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {ordersQuery.data && ordersQuery.data.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {ordersQuery.data.map((order) => (
              <Badge key={order.id} variant="secondary">
                {order.test.name}
              </Badge>
            ))}
          </div>
        )}

        <div className="relative max-w-sm">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search a lab test to order…" />
          {query.trim().length >= 2 && (isFetching || (testResults?.items.length ?? 0) > 0) && (
            <div className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border bg-popover shadow-md">
              {isFetching && <p className="px-2 py-1.5 text-xs text-muted-foreground">Searching…</p>}
              {!isFetching &&
                testResults?.items.map((test) => (
                  <button
                    key={test.id}
                    type="button"
                    className="flex w-full items-center justify-between px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                    onClick={() => void orderTest(test.id, test.name)}
                  >
                    <span>{test.name}</span>
                    <span className="text-xs text-muted-foreground">₹{test.price}</span>
                  </button>
                ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
