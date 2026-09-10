// Mirrors backend/app/modules/appointments/schemas.py — keep in sync with that file.

export const APPOINTMENT_STATUSES = ['SCHEDULED', 'CHECKED_IN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'NO_SHOW'] as const
export type AppointmentStatus = (typeof APPOINTMENT_STATUSES)[number]

export interface AppointmentSummary {
  id: string
  tenant_id: string
  branch_id: string
  patient_id: string
  doctor_id: string | null
  source: string
  scheduled_at: string
  duration_minutes: number
  status: string
  notes: string | null
  cancelled_reason: string | null
  cancelled_at: string | null
}

export interface AppointmentListResponse {
  items: AppointmentSummary[]
  total: number
  limit: number
  offset: number
}

export interface AppointmentSearchParams {
  patientId?: string
  doctorId?: string
  branchId?: string
  status?: string
  dateFrom?: string
  dateTo?: string
  limit?: number
  offset?: number
}

export interface AppointmentCreateRequest {
  patient_id: string
  branch_id: string
  doctor_id: string
  scheduled_at: string
  duration_minutes?: number
  notes?: string | null
}

// Patient self-booking (POST /appointments/me) — no patient_id, it's
// derived server-side from the caller's own linked Patient record.
export interface MyAppointmentCreateRequest {
  branch_id: string
  doctor_id: string
  scheduled_at: string
  duration_minutes?: number
  notes?: string | null
}

export interface AppointmentRescheduleRequest {
  scheduled_at?: string
  duration_minutes?: number
  doctor_id?: string
  branch_id?: string
  notes?: string | null
}

export interface AppointmentCancelRequest {
  reason: string
}
