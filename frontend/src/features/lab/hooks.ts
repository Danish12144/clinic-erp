import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addLabResults,
  cancelLabOrder,
  collectSample,
  completeLabOrder,
  createLabOrder,
  createLabTest,
  getLabOrder,
  listLabOrdersForEncounter,
  searchLabOrders,
  searchLabTests,
  searchLabTestsFull,
  updateLabTest,
} from '@/features/lab/api'
import { useAuth } from '@/features/auth/auth-context'
import type {
  LabOrderCancelRequest,
  LabOrderCreateRequest,
  LabOrderSearchParams,
  LabResultCreateRequest,
  LabTestCreateRequest,
  LabTestSearchParams,
  LabTestUpdateRequest,
} from '@/features/lab/types'
import { useDebouncedValue } from '@/lib/use-debounced-value'

// The whole Lab module is gated behind a per-tenant features.lab_enabled
// flag with no client-readable toggle (backend/app/modules/lab/router.py) —
// a clinic that hasn't opted in 403s on every route regardless of
// permissions. retry:false + isError (checked by callers) is how a
// caller decides to hide the lab section entirely rather than showing an
// error for an intentionally-off optional feature.
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

export function useLabTestCatalog(params: LabTestSearchParams) {
  return useQuery({
    queryKey: ['lab', 'tests', 'catalog', params],
    queryFn: () => searchLabTestsFull(params),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

function useInvalidateLabTests() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['lab', 'tests'] })
}

export function useCreateLabTest() {
  const invalidate = useInvalidateLabTests()
  return useMutation({ mutationFn: (payload: LabTestCreateRequest) => createLabTest(payload), onSuccess: invalidate })
}

export function useUpdateLabTest() {
  const invalidate = useInvalidateLabTests()
  return useMutation({
    mutationFn: ({ testId, payload }: { testId: string; payload: LabTestUpdateRequest }) => updateLabTest(testId, payload),
    onSuccess: invalidate,
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

export function useLabOrders(params: LabOrderSearchParams) {
  return useQuery({
    queryKey: ['lab', 'orders', 'search', params],
    queryFn: () => searchLabOrders(params),
    retry: false,
    placeholderData: keepPreviousData,
  })
}

export function useLabOrder(orderId: string | undefined) {
  return useQuery({
    queryKey: ['lab', 'orders', 'get', orderId],
    queryFn: () => getLabOrder(orderId!),
    enabled: Boolean(orderId),
  })
}

export function useCreateLabOrder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LabOrderCreateRequest) => createLabOrder(payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['lab', 'orders', 'by-encounter', variables.encounter_id] })
      void queryClient.invalidateQueries({ queryKey: ['lab', 'orders', 'search'] })
    },
  })
}

function useInvalidateLabOrder(orderId: string) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: ['lab', 'orders', 'get', orderId] })
    void queryClient.invalidateQueries({ queryKey: ['lab', 'orders', 'search'] })
  }
}

export function useCollectSample(orderId: string) {
  const invalidate = useInvalidateLabOrder(orderId)
  return useMutation({ mutationFn: () => collectSample(orderId), onSuccess: invalidate })
}

export function useAddLabResults(orderId: string) {
  const invalidate = useInvalidateLabOrder(orderId)
  return useMutation({
    mutationFn: (payload: LabResultCreateRequest) => addLabResults(orderId, payload),
    onSuccess: invalidate,
  })
}

export function useCompleteLabOrder(orderId: string) {
  const invalidate = useInvalidateLabOrder(orderId)
  return useMutation({ mutationFn: () => completeLabOrder(orderId), onSuccess: invalidate })
}

export function useCancelLabOrder(orderId: string) {
  const invalidate = useInvalidateLabOrder(orderId)
  return useMutation({
    mutationFn: (payload: LabOrderCancelRequest) => cancelLabOrder(orderId, payload),
    onSuccess: invalidate,
  })
}
