// Mirrors backend/app/modules/doctors/schemas.py — keep in sync with that file.

// Mirrors backend/app/modules/tenancy/schemas.py::WorkingHours/DayHours —
// a day-code -> {open, close} map (24h "HH:MM"); an omitted/null day means
// closed. Used by features/appointments to compute a slot grid client-side
// (backend/app/modules/appointments/service.py::_validate_slot is the
// actual source of truth at booking time; this is a preview only).
export interface DayHours {
  open: string
  close: string
}

export interface WorkingHours {
  mon?: DayHours | null
  tue?: DayHours | null
  wed?: DayHours | null
  thu?: DayHours | null
  fri?: DayHours | null
  sat?: DayHours | null
  sun?: DayHours | null
}

export interface DoctorDirectoryEntry {
  user_id: string
  first_name: string | null
  last_name: string | null
  specialization: string | null
  consultation_fee: string | null
  working_hours: WorkingHours
  slot_duration_minutes: number
  branch_ids: string[]
}

export interface DoctorDirectoryResponse {
  items: DoctorDirectoryEntry[]
  total: number
  limit: number
  offset: number
}

export interface DoctorSummary {
  user_id: string
  tenant_id: string
  first_name: string | null
  last_name: string | null
  email: string | null
  phone: string | null
  status: string
  specialization: string | null
  registration_number: string | null
  consultation_fee: string | null
  working_hours: WorkingHours
  slot_duration_minutes: number
  branch_ids: string[]
  created_at: string
  updated_at: string
}

export interface DoctorListResponse {
  items: DoctorSummary[]
  total: number
  limit: number
  offset: number
}

export interface InviteInfo {
  // Exactly one of debug_invite_token/temporary_password is ever set, never
  // both — see backend/app/modules/auth/service.py::issue_staff_invite.
  invite_expires_at: string | null
  debug_invite_token: string | null
  temporary_password: string | null
}

export interface DoctorCreateRequest {
  first_name: string
  last_name?: string | null
  email?: string | null
  phone?: string | null
  specialization?: string | null
  registration_number?: string | null
  consultation_fee?: number | null
  slot_duration_minutes?: number
  bio?: string | null
  branch_ids?: string[]
}

export interface DoctorCreateResponse {
  doctor: DoctorSummary
  invite: InviteInfo
}

// PATCH /doctors/{user_id} (staff.manage) and PATCH /doctors/me
// (doctor.manage_own_profile) share this same request shape — see
// backend/app/modules/doctors/schemas.py::DoctorUpdateRequest. Every field
// optional; omit a field to leave it unchanged.
export interface DoctorUpdateRequest {
  first_name?: string | null
  last_name?: string | null
  specialization?: string | null
  registration_number?: string | null
  consultation_fee?: number | null
  working_hours?: WorkingHours | null
  slot_duration_minutes?: number | null
  bio?: string | null
}

export interface BranchAssignmentRequest {
  branch_ids: string[]
}
