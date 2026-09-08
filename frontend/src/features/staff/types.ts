// Mirrors backend/app/modules/staff/schemas.py — keep in sync with that file.
// Deliberately excludes OWNER/DOCTOR/PATIENT — see the backend module's own
// docstring: Owner isn't provisioned via any staff-account flow, Doctor has
// its own module (see features/doctors), Patient isn't staff at all.
export const STAFF_ROLE_CODES = ['RECEPTIONIST', 'NURSE', 'LAB_STAFF', 'PHARMACY_STAFF', 'OTHER_STAFF'] as const
export type StaffRoleCode = (typeof STAFF_ROLE_CODES)[number]

export interface StaffSummary {
  user_id: string
  tenant_id: string
  role_code: string
  first_name: string | null
  last_name: string | null
  email: string | null
  phone: string | null
  status: string
  employee_code: string | null
  designation: string | null
  branch_ids: string[]
  created_at: string
  updated_at: string
}

export interface StaffListResponse {
  items: StaffSummary[]
  total: number
  limit: number
  offset: number
}

export interface InviteInfo {
  invite_expires_at: string
  debug_invite_token: string | null
}

export interface StaffCreateRequest {
  role_code: StaffRoleCode
  first_name: string
  last_name?: string | null
  email?: string | null
  phone?: string | null
  designation?: string | null
  branch_ids?: string[]
}

export interface StaffCreateResponse {
  staff: StaffSummary
  invite: InviteInfo
}
