// Mirrors backend/app/modules/auth/schemas.py's PermissionOverride* shapes.

export interface PermissionOverrideSummary {
  id: string
  tenant_id: string
  role_code: string | null
  user_id: string | null
  permission_code: string
  granted: boolean
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface PermissionOverrideListResponse {
  items: PermissionOverrideSummary[]
  total: number
  limit: number
  offset: number
}

export interface PermissionOverrideSetRequest {
  role_code?: string | null
  user_id?: string | null
  permission_code: string
  granted: boolean
}
