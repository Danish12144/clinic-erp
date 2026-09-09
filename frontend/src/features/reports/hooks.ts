import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/auth-context'
import { getBillingSummary, getFinancialReport } from '@/features/reports/api'
import type { ReportQueryParams } from '@/features/reports/types'

const DASHBOARD_PERMS = ['dashboard.view', 'dashboard.view_own']

// period=custom requires both dateFrom/dateTo (the backend 422s otherwise) —
// gate the query so a half-picked custom range doesn't fire a doomed request.
function isQueryReady(params: ReportQueryParams): boolean {
  return params.period !== 'custom' || Boolean(params.dateFrom && params.dateTo)
}

export function useBillingSummary(params: ReportQueryParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['reports', 'billing-summary', params],
    queryFn: () => getBillingSummary(params),
    enabled: DASHBOARD_PERMS.some(hasPermission) && isQueryReady(params),
  })
}

export function useFinancialReport(params: ReportQueryParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['reports', 'financial', params],
    queryFn: () => getFinancialReport(params),
    enabled: DASHBOARD_PERMS.some(hasPermission) && isQueryReady(params),
  })
}
