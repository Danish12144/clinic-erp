// Mirrors backend/app/modules/lab/schemas.py — only the fields the OPD
// pad's optional lab-order section needs.

export interface LabTestSummary {
  id: string
  name: string
  test_code: string | null
  category: string | null
  price: string
  is_active: boolean
}

export interface LabTestListResponse {
  items: LabTestSummary[]
  total: number
  limit: number
  offset: number
}

export interface LabOrderCreateRequest {
  encounter_id: string
  test_id: string
}

export interface LabOrderSummary {
  id: string
  encounter_id: string
  patient_id: string
  doctor_id: string | null
  test: LabTestSummary
  status: string
  ordered_at: string
}
