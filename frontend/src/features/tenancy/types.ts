// Mirrors backend/app/modules/tenancy/schemas.py — only the fields the
// Admin Settings page actually reads/writes (working_hours is left as
// `unknown` since the page doesn't edit it yet).

export interface ClinicSummary {
  id: string
  name: string
  slug: string
  timezone: string
  locale: string
  gst_number: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface ClinicUpdateRequest {
  name?: string
  timezone?: string
  locale?: string
  gst_number?: string | null
}

export interface TenantSettingSummary {
  key: string
  value: unknown
  created_at: string
  updated_at: string
}
