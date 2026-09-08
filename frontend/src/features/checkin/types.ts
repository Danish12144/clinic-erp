// Mirrors backend/app/modules/checkin/schemas.py — keep in sync with that file.

export interface WalkInRequest {
  patient_id: string
  branch_id: string
  doctor_id?: string | null
  notes?: string | null
}

export interface QueueTokenSummary {
  id: string
  tenant_id: string
  branch_id: string
  encounter_id: string
  doctor_id: string | null
  token_date: string
  token_number: number
  status: string
  called_at: string | null
}

export interface EncounterSummary {
  id: string
  tenant_id: string
  branch_id: string
  appointment_id: string | null
  patient_id: string
  status: string
  checked_in_at: string
  completed_at: string | null
}

export interface CheckInResult {
  // appointment omitted — not used by the registration flow's UI today.
  encounter: EncounterSummary
  queue_token: QueueTokenSummary
}

export const ACTIVE_QUEUE_STATUSES = ['WAITING', 'CALLED', 'IN_PROGRESS'] as const

export interface QueueListResponse {
  items: QueueTokenSummary[]
  total: number
  limit: number
  offset: number
}

export interface QueueSearchParams {
  branchId?: string
  doctorId?: string
  status?: string
  limit?: number
  offset?: number
}

export interface EncounterListResponse {
  items: EncounterSummary[]
  total: number
  limit: number
  offset: number
}

export interface EncounterSearchParams {
  branchId?: string
  patientId?: string
  status?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}
