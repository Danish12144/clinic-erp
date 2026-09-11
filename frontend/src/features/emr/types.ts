// Mirrors backend/app/modules/emr/schemas.py — keep in sync with that file.
// Reuses PrescriptionSummary/VitalsSummary from their own feature modules
// rather than redefining them here, same as PatientEmrTimeline itself
// composes those two modules' schemas on the backend.

import type { PrescriptionSummary } from '@/features/consultations/types'
import type { VitalsSummary } from '@/features/vitals/types'

export interface EmrVisitEntry {
  encounter_id: string
  branch_id: string
  encounter_status: string
  checked_in_at: string
  completed_at: string | null
  consultation_id: string
  doctor_id: string
  chief_complaint: string | null
  diagnosis_text: string | null
  icd10_code: string | null
  clinical_notes: string | null
  started_at: string | null
  ended_at: string | null
}

// storage_key is deliberately not a download link here — see
// portal-medical-records-page.tsx's own comment for why this table's
// documents aren't wired to a resolvable download endpoint yet.
export interface MedicalDocumentSummary {
  id: string
  patient_id: string
  encounter_id: string | null
  document_type: string
  title: string
  storage_key: string
  mime_type: string | null
  file_size_bytes: number | null
  notes: string | null
  uploaded_by: string
  created_at: string
}

export interface PatientEmrTimeline {
  patient_id: string
  visits: EmrVisitEntry[]
  prescriptions: PrescriptionSummary[]
  vitals: VitalsSummary[]
  documents: MedicalDocumentSummary[]
}
