import { apiClient } from '@/lib/api-client'
import type { VitalsCreateRequest, VitalsListResponse, VitalsSummary } from '@/features/vitals/types'

export async function recordVitals(payload: VitalsCreateRequest): Promise<VitalsSummary> {
  const { data } = await apiClient.post<VitalsSummary>('/vitals', payload)
  return data
}

export async function listVitalsForEncounter(encounterId: string): Promise<VitalsListResponse> {
  const { data } = await apiClient.get<VitalsListResponse>('/vitals', { params: { encounter_id: encounterId } })
  return data
}
