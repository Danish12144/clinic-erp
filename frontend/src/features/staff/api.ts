import { apiClient } from '@/lib/api-client'
import type { StaffCreateRequest, StaffCreateResponse, StaffListResponse } from '@/features/staff/types'

export async function listStaff(params: { q?: string; includeInactive?: boolean }): Promise<StaffListResponse> {
  const { data } = await apiClient.get<StaffListResponse>('/staff', {
    params: { q: params.q || undefined, include_inactive: params.includeInactive ?? false, limit: 100 },
  })
  return data
}

export async function createStaff(payload: StaffCreateRequest): Promise<StaffCreateResponse> {
  const { data } = await apiClient.post<StaffCreateResponse>('/staff', payload)
  return data
}
