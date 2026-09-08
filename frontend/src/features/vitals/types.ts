// Mirrors backend/app/modules/vitals/schemas.py — keep in sync with that file.
// The OPD pad only ever collects BP/Pulse/Temperature/Weight — spo2/
// height_cm exist on the backend but aren't part of this screen's scope.

export interface VitalsCreateRequest {
  encounter_id: string
  systolic_bp?: number | null
  diastolic_bp?: number | null
  heart_rate?: number | null
  temperature_celsius?: number | null
  weight_kg?: number | null
  notes?: string | null
}

export interface VitalsSummary {
  id: string
  encounter_id: string
  patient_id: string
  recorded_by: string
  recorded_at: string
  systolic_bp: number | null
  diastolic_bp: number | null
  heart_rate: number | null
  temperature_celsius: number | null
  spo2: number | null
  weight_kg: number | null
  height_cm: number | null
  bmi: number | null
  notes: string | null
}

export interface VitalsListResponse {
  items: VitalsSummary[]
  total: number
  limit: number
  offset: number
}
