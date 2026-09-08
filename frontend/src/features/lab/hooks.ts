import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createLabOrder, listLabOrdersForEncounter, searchLabTests } from '@/features/lab/api'
import { useAuth } from '@/features/auth/auth-context'
import type { LabOrderCreateRequest } from '@/features/lab/types'
import { useDebouncedValue } from '@/lib/use-debounced-value'

// The whole Lab module is gated behind a per-tenant features.lab_enabled
// flag with no client-readable toggle (backend/app/modules/lab/router.py) —
// a clinic that hasn't opted in 403s on every route regardless of
// permissions. retry:false + isError (checked by callers) is how the OPD
// pad decides to hide the lab-order section entirely rather than showing
// an error for an intentionally-off optional feature.
export function useLabTestSearch(rawQuery: string) {
  const { hasPermission } = useAuth()
  const debounced = useDebouncedValue(rawQuery, 300)

  return useQuery({
    queryKey: ['lab', 'tests', 'search', debounced],
    queryFn: () => searchLabTests(debounced),
    enabled: hasPermission('lab.order') && debounced.trim().length >= 2,
    retry: false,
  })
}

export function useEncounterLabOrders(encounterId: string | undefined) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['lab', 'orders', 'by-encounter', encounterId],
    queryFn: () => listLabOrdersForEncounter(encounterId!),
    enabled: Boolean(encounterId) && hasPermission('lab.view_results'),
    retry: false,
  })
}

export function useCreateLabOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LabOrderCreateRequest) => createLabOrder(payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['lab', 'orders', 'by-encounter', variables.encounter_id] })
    },
  })
}
