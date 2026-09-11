// Mirrors backend/app/modules/audit/schemas.py.

export interface AuditLogEntry {
  id: string
  actor_user_id: string | null
  actor_role: string | null
  action: string
  entity_type: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
  limit: number
  offset: number
}
