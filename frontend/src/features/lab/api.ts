import { apiClient } from '@/lib/api-client'
import type {
  LabOrderCancelRequest,
  LabOrderCreateRequest,
  LabOrderListResponse,
  LabOrderSearchParams,
  LabOrderSummary,
  LabResultCreateRequest,
  LabTestCreateRequest,
  LabTestListResponse,
  LabTestSearchParams,
  LabTestSummary,
  LabTestUpdateRequest,
} from '@/features/lab/types'

// Kept for the OPD pad's lightweight lab-test-order search — a narrower
// call shape than the full catalog search below.
export async function searchLabTests(query: string): Promise<LabTestListResponse> {
  const { data } = await apiClient.get<LabTestListResponse>('/lab/tests', {
    params: { q: query || undefined, is_active: true, limit: 20 },
  })
  return data
}

export async function searchLabTestsFull(params: LabTestSearchParams): Promise<LabTestListResponse> {
  const { data } = await apiClient.get<LabTestListResponse>('/lab/tests', {
    params: { q: params.q || undefined, is_active: params.isActive, limit: params.limit ?? 50, offset: params.offset ?? 0 },
  })
  return data
}

export async function createLabTest(payload: LabTestCreateRequest): Promise<LabTestSummary> {
  const { data } = await apiClient.post<LabTestSummary>('/lab/tests', payload)
  return data
}

export async function updateLabTest(testId: string, payload: LabTestUpdateRequest): Promise<LabTestSummary> {
  const { data } = await apiClient.patch<LabTestSummary>(`/lab/tests/${testId}`, payload)
  return data
}

export async function createLabOrder(payload: LabOrderCreateRequest): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>('/lab/orders', payload)
  return data
}

export async function searchLabOrders(params: LabOrderSearchParams): Promise<LabOrderListResponse> {
  const { data } = await apiClient.get<LabOrderListResponse>('/lab/orders', {
    params: {
      patient_id: params.patientId || undefined,
      encounter_id: params.encounterId || undefined,
      status: params.status || undefined,
      limit: params.limit ?? 30,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function listLabOrdersForEncounter(encounterId: string): Promise<LabOrderSummary[]> {
  const response = await searchLabOrders({ encounterId, limit: 30 })
  return response.items
}

export async function getLabOrder(orderId: string): Promise<LabOrderSummary> {
  const { data } = await apiClient.get<LabOrderSummary>(`/lab/orders/${orderId}`)
  return data
}

export async function collectSample(orderId: string): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>(`/lab/orders/${orderId}/collect-sample`)
  return data
}

export async function addLabResults(orderId: string, payload: LabResultCreateRequest): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>(`/lab/orders/${orderId}/results`, payload)
  return data
}

export async function completeLabOrder(orderId: string): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>(`/lab/orders/${orderId}/complete`)
  return data
}

export async function cancelLabOrder(orderId: string, payload: LabOrderCancelRequest): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>(`/lab/orders/${orderId}/cancel`, payload)
  return data
}
