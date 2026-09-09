// Mirrors backend/app/modules/lab/schemas.py — keep in sync with that file.

export interface ReferenceRangeEntry {
  min: number | null
  max: number | null
  unit: string | null
  sex: 'Male' | 'Female' | 'Other' | null
  age_min: number | null
  age_max: number | null
}

export interface LabTestSummary {
  id: string
  name: string
  test_code: string | null
  category: string | null
  specimen_type: string | null
  turnaround_hours: number | null
  price: string
  reference_ranges: ReferenceRangeEntry[]
  is_active: boolean
}

export interface LabTestListResponse {
  items: LabTestSummary[]
  total: number
  limit: number
  offset: number
}

export interface LabTestSearchParams {
  q?: string
  isActive?: boolean
  limit?: number
  offset?: number
}

export interface LabTestCreateRequest {
  name: string
  test_code?: string | null
  category?: string | null
  specimen_type?: string | null
  turnaround_hours?: number | null
  price?: string
  reference_ranges?: ReferenceRangeEntry[]
}

export interface LabTestUpdateRequest {
  name?: string
  test_code?: string | null
  category?: string | null
  specimen_type?: string | null
  turnaround_hours?: number | null
  price?: string
  reference_ranges?: ReferenceRangeEntry[]
  is_active?: boolean
}

export const LAB_ORDER_STATUSES = ['ORDERED', 'SAMPLE_COLLECTED', 'RESULTED', 'COMPLETED', 'CANCELLED'] as const
export type LabOrderStatus = (typeof LAB_ORDER_STATUSES)[number]

export interface LabOrderCreateRequest {
  encounter_id: string
  test_id: string
  doctor_id?: string | null
}

export interface LabOrderCancelRequest {
  reason: string
}

export interface LabResultEntry {
  parameter: string
  value: string
  unit?: string | null
  flag_override?: string | null
}

export interface LabResultCreateRequest {
  results: LabResultEntry[]
}

export interface LabResultSummary {
  id: string
  lab_order_id: string
  parameter: string
  value: string
  unit: string | null
  reference_range: string | null
  flag: string
  entered_by: string
  finalized_at: string | null
  created_at: string
}

export interface LabOrderSummary {
  id: string
  tenant_id: string
  encounter_id: string
  patient_id: string
  doctor_id: string | null
  test: LabTestSummary
  ordered_by: string
  status: string
  ordered_at: string
  sample_collected_at: string | null
  resulted_at: string | null
  completed_at: string | null
  cancelled_at: string | null
  cancelled_reason: string | null
  results: LabResultSummary[]
}

export interface LabOrderListResponse {
  items: LabOrderSummary[]
  total: number
  limit: number
  offset: number
}

export interface LabOrderSearchParams {
  patientId?: string
  encounterId?: string
  status?: string
  limit?: number
  offset?: number
}
