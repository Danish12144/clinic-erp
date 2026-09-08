import { apiClient } from '@/lib/api-client'
import type { FollowUpCreateRequest, FollowUpSummary } from '@/features/followups/types'

export async function createFollowUp(payload: FollowUpCreateRequest): Promise<FollowUpSummary> {
  const { data } = await apiClient.post<FollowUpSummary>('/crm/follow-ups', payload)
  return data
}
