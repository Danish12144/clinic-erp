import { apiClient } from '@/lib/api-client'
import type { PermissionOverrideListResponse, PermissionOverrideSetRequest } from '@/features/permissions/types'

export async function searchPermissionOverrides(): Promise<PermissionOverrideListResponse> {
  const { data } = await apiClient.get<PermissionOverrideListResponse>('/permission-overrides', { params: { limit: 200 } })
  return data
}

export async function setPermissionOverride(payload: PermissionOverrideSetRequest) {
  const { data } = await apiClient.put('/permission-overrides', payload)
  return data
}

export async function deletePermissionOverride(overrideId: string): Promise<void> {
  await apiClient.delete(`/permission-overrides/${overrideId}`)
}
