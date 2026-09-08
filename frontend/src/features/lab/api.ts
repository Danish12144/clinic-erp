import { apiClient } from '@/lib/api-client'
import type { LabOrderCreateRequest, LabOrderSummary, LabTestListResponse } from '@/features/lab/types'

export async function searchLabTests(query: string): Promise<LabTestListResponse> {
  const { data } = await apiClient.get<LabTestListResponse>('/lab/tests', {
    params: { q: query || undefined, is_active: true, limit: 20 },
  })
  return data
}

export async function createLabOrder(payload: LabOrderCreateRequest): Promise<LabOrderSummary> {
  const { data } = await apiClient.post<LabOrderSummary>('/lab/orders', payload)
  return data
}

export async function listLabOrdersForEncounter(encounterId: string): Promise<LabOrderSummary[]> {
  const { data } = await apiClient.get<{ items: LabOrderSummary[] }>('/lab/orders', { params: { encounter_id: encounterId } })
  return data.items
}
