import { apiClient } from '@/lib/api-client'
import type { BillingSummary, FinancialReport, ReportQueryParams } from '@/features/reports/types'

function toQueryParams(params: ReportQueryParams) {
  return {
    period: params.period,
    date_from: params.dateFrom || undefined,
    date_to: params.dateTo || undefined,
    branch_id: params.branchId || undefined,
    doctor_id: params.doctorId || undefined,
  }
}

export async function getBillingSummary(params: ReportQueryParams): Promise<BillingSummary> {
  const { data } = await apiClient.get<BillingSummary>('/billing/summary', { params: toQueryParams(params) })
  return data
}

export async function getFinancialReport(params: ReportQueryParams): Promise<FinancialReport> {
  const { data } = await apiClient.get<FinancialReport>('/reports/financial', { params: toQueryParams(params) })
  return data
}

// Phase 1 (Master Handoff item 6) — same filters as getFinancialReport, a
// CSV file instead of JSON.
export async function exportFinancialReportCsv(params: ReportQueryParams): Promise<Blob> {
  const { data } = await apiClient.get<Blob>('/reports/financial/export', {
    params: toQueryParams(params),
    responseType: 'blob',
  })
  return data
}
