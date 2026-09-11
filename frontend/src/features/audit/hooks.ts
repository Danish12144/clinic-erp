import { useQuery } from '@tanstack/react-query'
import { searchAuditLogs, type AuditLogSearchParams } from '@/features/audit/api'

export function useAuditLogSearch(params: AuditLogSearchParams) {
  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => searchAuditLogs(params),
    placeholderData: (prev) => prev,
  })
}
