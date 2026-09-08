// Mirrors backend/app/modules/tenancy/schemas.py::BranchSummary.

export interface BranchSummary {
  id: string
  tenant_id: string
  name: string
  address: string | null
  phone: string | null
  timezone: string | null
  is_active: boolean
}
