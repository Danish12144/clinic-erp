// Mirrors backend/app/modules/auth/schemas.py — keep in sync with that file.

export const ROLE_CODES = [
  'OWNER',
  'DOCTOR',
  'RECEPTIONIST',
  'NURSE',
  'LAB_STAFF',
  'PHARMACY_STAFF',
  'OTHER_STAFF',
  'PATIENT',
] as const

export type RoleCode = (typeof ROLE_CODES)[number]

export interface UserSummary {
  id: string
  tenant_id: string
  first_name: string | null
  last_name: string | null
  email: string | null
  phone: string | null
  role_code: RoleCode
  status: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: UserSummary
}

export interface AccessTokenOnlyResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface MeResponse {
  user: UserSummary
  permissions: string[]
}

export interface StaffLoginRequest {
  clinic_slug: string
  identifier: string
  password: string
}

export interface OtpRequestPayload {
  clinic_slug: string
  phone: string
}

export interface OtpVerifyPayload {
  clinic_slug: string
  phone: string
  code: string
}
