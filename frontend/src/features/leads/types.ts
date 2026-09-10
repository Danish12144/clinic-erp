// Mirrors backend/app/modules/leads/schemas.py + models.py — keep in sync with those files.

export const LEAD_SOURCES = ['GOOGLE_AD', 'WALK_IN', 'WEBSITE', 'REFERRAL', 'SOCIAL'] as const
export type LeadSource = (typeof LEAD_SOURCES)[number]

export const LEAD_SOURCE_LABELS: Record<LeadSource, string> = {
  GOOGLE_AD: 'Google Ad',
  WALK_IN: 'Walk-in',
  WEBSITE: 'Website',
  REFERRAL: 'Referral',
  SOCIAL: 'Social',
}

// Pipeline order — mirrors the columns rendered on the Leads board.
export const LEAD_STATUSES = ['NEW', 'CONTACTED', 'APPOINTMENT_SCHEDULED', 'CONVERTED', 'LOST'] as const
export type LeadStatus = (typeof LEAD_STATUSES)[number]

export const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  NEW: 'New',
  CONTACTED: 'Contacted',
  APPOINTMENT_SCHEDULED: 'Appt. scheduled',
  CONVERTED: 'Converted',
  LOST: 'Lost',
}

// Statuses PATCH /leads/{id} may set directly — CONVERTED is only ever
// reachable through POST /leads/{id}/convert (backend rejects a direct
// PATCH to CONVERTED with a 422), so it's excluded here on purpose.
export const LEAD_MANUAL_STATUSES = ['NEW', 'CONTACTED', 'APPOINTMENT_SCHEDULED', 'LOST'] as const

// Statuses a lead can still be converted from — matches
// LeadService.convert_lead's own allowed-status check.
export const LEAD_CONVERTIBLE_STATUSES = ['NEW', 'CONTACTED', 'APPOINTMENT_SCHEDULED'] as const

export const LEAD_INTERACTION_TYPES = ['CALL', 'WHATSAPP', 'NOTE', 'EMAIL'] as const
export type LeadInteractionType = (typeof LEAD_INTERACTION_TYPES)[number]

export interface LeadSummary {
  id: string
  tenant_id: string
  first_name: string
  last_name: string | null
  phone: string | null
  email: string | null
  source: LeadSource | null
  status: LeadStatus
  assigned_to_user_id: string | null
  notes: string | null
  converted_patient_id: string | null
  created_at: string
  updated_at: string
}

export interface LeadListResponse {
  items: LeadSummary[]
  total: number
  limit: number
  offset: number
}

export interface LeadSearchParams {
  status?: LeadStatus
  source?: LeadSource
  limit?: number
  offset?: number
}

export interface LeadCreateRequest {
  first_name: string
  last_name?: string
  phone?: string
  email?: string
  source?: LeadSource
  notes?: string
}

export interface LeadUpdateRequest {
  first_name?: string
  last_name?: string
  phone?: string
  email?: string
  source?: LeadSource
  status?: (typeof LEAD_MANUAL_STATUSES)[number]
  notes?: string
}

export interface LeadInteractionCreateRequest {
  interaction_type: LeadInteractionType
  outcome?: string
  notes?: string
}

export interface LeadInteractionSummary {
  id: string
  tenant_id: string
  lead_id: string
  interaction_type: LeadInteractionType
  outcome: string | null
  notes: string | null
  performed_by: string
  created_at: string
}

export interface LeadConvertRequest {
  gender?: 'Male' | 'Female' | 'Other'
  date_of_birth?: string
  address?: string
}

export interface LeadConvertResponse {
  lead: LeadSummary
  patient_id: string
}
