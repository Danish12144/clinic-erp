// Mirrors backend/app/modules/reports/schemas.py — keep in sync with that file.

export const REPORT_PERIODS = ['today', '7_days', '30_days', 'all_time', 'custom'] as const
export type ReportPeriod = (typeof REPORT_PERIODS)[number]

export interface ReportQueryParams {
  period: ReportPeriod
  dateFrom?: string
  dateTo?: string
  branchId?: string
  doctorId?: string
}

export interface PaymentModeAmount {
  method: string
  collected: string
  refunded: string
}

export interface ServiceTypeRevenue {
  source_type: string
  total_billed: string
}

export interface BillingSummary {
  period: string
  date_from: string | null
  date_to: string | null
  total_collected: string
  total_bills_raised: number
  payment_modes_tracked: number
  total_refunds: string
  by_payment_mode: PaymentModeAmount[]
}

export interface FinancialReport {
  period: string
  date_from: string | null
  date_to: string | null
  total_billed: string
  total_collected: string
  total_refunded: string
  net_collected: string
  by_service_type: ServiceTypeRevenue[]
  by_payment_mode: PaymentModeAmount[]
}
