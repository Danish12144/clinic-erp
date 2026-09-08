import { apiClient } from '@/lib/api-client'
import type {
  CheckInResult,
  EncounterListResponse,
  EncounterSearchParams,
  EncounterSummary,
  QueueListResponse,
  QueueSearchParams,
  QueueTokenSummary,
  WalkInRequest,
} from '@/features/checkin/types'

export async function registerWalkIn(payload: WalkInRequest): Promise<CheckInResult> {
  const { data } = await apiClient.post<CheckInResult>('/encounters/walk-in', payload)
  return data
}

export async function searchEncounters(params: EncounterSearchParams): Promise<EncounterListResponse> {
  const { data } = await apiClient.get<EncounterListResponse>('/encounters', {
    params: {
      branch_id: params.branchId || undefined,
      patient_id: params.patientId || undefined,
      status: params.status || undefined,
      date_from: params.dateFrom || undefined,
      date_to: params.dateTo || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function searchQueue(params: QueueSearchParams): Promise<QueueListResponse> {
  const { data } = await apiClient.get<QueueListResponse>('/queue', {
    params: {
      branch_id: params.branchId || undefined,
      doctor_id: params.doctorId || undefined,
      status: params.status || undefined,
      limit: params.limit ?? 100,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getEncounter(encounterId: string): Promise<EncounterSummary> {
  const { data } = await apiClient.get<EncounterSummary>(`/encounters/${encounterId}`)
  return data
}

// Only reachable by roles holding queue.manage (Owner/Receptionist) —
// Doctor does NOT hold this permission (see backend/app/modules/checkin/router.py),
// so the OPD workspace never calls this for a Doctor-role caller.
export async function updateQueueTokenStatus(tokenId: string, status: string): Promise<QueueTokenSummary> {
  const { data } = await apiClient.patch<QueueTokenSummary>(`/queue/${tokenId}`, { status })
  return data
}
