// Mirrors backend/app/modules/crm/schemas.py — only what the OPD pad's
// optional follow-up scheduler needs. doctor_id is deliberately omitted —
// the backend forces it to the caller for a Doctor-role request regardless
// of what's sent (see backend/app/modules/crm/service.py).

export interface FollowUpCreateRequest {
  patient_id: string
  encounter_id?: string | null
  due_at: string
  reason?: string | null
}

export interface FollowUpSummary {
  id: string
  patient_id: string
  doctor_id: string | null
  encounter_id: string | null
  due_at: string
  status: string
  reason: string | null
}
