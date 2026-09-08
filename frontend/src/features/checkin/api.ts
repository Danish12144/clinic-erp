import { apiClient } from '@/lib/api-client'
import type { CheckInResult, WalkInRequest } from '@/features/checkin/types'

export async function registerWalkIn(payload: WalkInRequest): Promise<CheckInResult> {
  const { data } = await apiClient.post<CheckInResult>('/encounters/walk-in', payload)
  return data
}
