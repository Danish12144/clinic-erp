// Mirrors backend/app/modules/public/schemas.py — the public (unauthenticated)
// clinic discovery + self-booking surface, Phase 2 (Master Handoff item 1).

export interface PublicClinicSummary {
  slug: string
  name: string
  timezone: string
}

export interface PublicBranchSummary {
  id: string
  name: string
  address: string | null
  phone: string | null
}

export interface PublicDoctorSummary {
  user_id: string
  first_name: string | null
  last_name: string | null
  specialization: string | null
  consultation_fee: string | null
  slot_duration_minutes: number
  branch_ids: string[]
}

export interface PublicSlot {
  scheduled_at: string
  duration_minutes: number
}

export interface PublicSlotsResponse {
  date: string
  slots: PublicSlot[]
}

export interface PublicBookingRequest {
  branch_id: string
  doctor_id: string
  scheduled_at: string
  first_name: string
  last_name?: string | null
  phone: string
  email?: string | null
  request_prepayment?: boolean
  prepayment_amount?: string | null
}

export interface PublicGatewayOrderInfo {
  provider: string
  order_id: string
  amount: string
  currency: string
  key_id: string
}

export interface PublicBookingResponse {
  appointment_id: string
  patient_id: string
  scheduled_at: string
  duration_minutes: number
  status: string
  payment_status: string
  gateway_order: PublicGatewayOrderInfo | null
}

export interface PublicRetryPaymentRequest {
  phone: string
}
