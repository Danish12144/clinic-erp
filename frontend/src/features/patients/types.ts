// Mirrors backend/app/modules/patients/schemas.py — keep in sync with that file.

export type Gender = 'Male' | 'Female' | 'Other'
export type BloodGroup = 'A+' | 'A-' | 'B+' | 'B-' | 'AB+' | 'AB-' | 'O+' | 'O-'

export interface EmergencyContact {
  name: string
  phone: string
  relationship: string
}

export interface PatientSummary {
  id: string
  tenant_id: string
  mrn: string
  first_name: string
  last_name: string | null
  gender: Gender | null
  date_of_birth: string | null
  phone: string | null
  email: string | null
  blood_group: BloodGroup | null
  allergies: string[]
  chronic_conditions: string[]
  emergency_contact: EmergencyContact | null
  address: string | null
  abha_id: string | null
  abha_address: string | null
  created_at: string
  updated_at: string
}

export interface PatientCreateRequest {
  first_name: string
  last_name?: string | null
  gender?: Gender | null
  date_of_birth?: string | null
  phone?: string | null
  email?: string | null
  blood_group?: BloodGroup | null
  allergies?: string[]
  chronic_conditions?: string[]
  address?: string | null
  abha_id?: string | null
  abha_address?: string | null
}

// PATCH /patients/{id} (patients.register) — every field optional, mirrors
// backend/app/modules/patients/schemas.py::PatientUpdateRequest. Omit a
// field to leave it unchanged; emergency_contact isn't editable from any
// screen yet, so it's left out here rather than half-wired.
export interface PatientUpdateRequest {
  first_name?: string
  last_name?: string | null
  gender?: Gender | null
  date_of_birth?: string | null
  phone?: string | null
  email?: string | null
  blood_group?: BloodGroup | null
  allergies?: string[]
  chronic_conditions?: string[]
  address?: string | null
  abha_id?: string | null
  abha_address?: string | null
}

export interface PatientCreateResponse {
  patient: PatientSummary
  possible_duplicates: PatientSummary[]
}

export interface PatientListResponse {
  items: PatientSummary[]
  total: number
  limit: number
  offset: number
}

export interface PatientSearchParams {
  q?: string
  phone?: string
  mrn?: string
  limit?: number
  offset?: number
}
