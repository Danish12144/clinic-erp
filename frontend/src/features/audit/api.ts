import { apiClient } from '@/lib/api-client'
import type { AuditLogListResponse } from '@/features/audit/types'

export interface AuditLogSearchParams {
  entityType?: string
  entityId?: string
  actorUserId?: string
  limit?: number
  offset?: number
}

export async function searchAuditLogs(params: AuditLogSearchParams): Promise<AuditLogListResponse> {
  const { data } = await apiClient.get<AuditLogListResponse>('/audit-logs', {
    params: {
      entity_type: params.entityType,
      entity_id: params.entityId,
      actor_user_id: params.actorUserId,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })
  return data
}
