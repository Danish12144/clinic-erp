// Mirrors backend/app/modules/doctors/schemas.py — keep in sync with that file.

export interface DoctorDirectoryEntry {
  user_id: string
  first_name: string | null
  last_name: string | null
  specialization: string | null
  consultation_fee: string | null
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
  invite_expires_at: string
  debug_invite_token: string | null
}

export interface DoctorCreateRequest {
  first_name: string
  last_name?: string | null
  email?: string | null
  phone?: string | null
  specialization?: string | null
  registration_number?: string | null
  consultation_fee?: number | null
  bio?: string | null
  branch_ids?: string[]
}

export interface DoctorCreateResponse {
  doctor: DoctorSummary
  invite: InviteInfo
}
