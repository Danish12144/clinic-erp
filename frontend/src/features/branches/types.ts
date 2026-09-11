// Mirrors backend/app/modules/tenancy/schemas.py::BranchSummary and the
// create/update request bodies (working_hours is left as `unknown` since
// no screen edits it yet — branches default to an empty/closed schedule).

export interface BranchSummary {
  id: string
  tenant_id: string
  name: string
  address: string | null
  phone: string | null
  timezone: string | null
  is_active: boolean
}

export interface BranchCreateRequest {
  name: string
  address?: string | null
  phone?: string | null
  timezone?: string | null
}

export interface BranchUpdateRequest {
  name?: string
  address?: string | null
  phone?: string | null
  timezone?: string | null
  is_active?: boolean
}
