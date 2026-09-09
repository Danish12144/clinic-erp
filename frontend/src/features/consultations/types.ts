// Mirrors backend/app/modules/consultation/schemas.py — keep in sync with that file.

export interface ConsultationSummary {
  id: string
  tenant_id: string
  encounter_id: string
  doctor_id: string
  chief_complaint: string | null
  clinical_notes: string | null
  diagnosis_text: string | null
  icd10_code: string | null
  started_at: string | null
  ended_at: string | null
}

export interface ConsultationListResponse {
  items: ConsultationSummary[]
  total: number
  limit: number
  offset: number
}

export interface ConsultationStartRequest {
  encounter_id: string
  chief_complaint?: string | null
}

export interface ConsultationUpdateRequest {
  chief_complaint?: string | null
  clinical_notes?: string | null
  diagnosis_text?: string | null
  icd10_code?: string | null
}

export interface PrescriptionItemCreateRequest {
  medicine_id?: string | null
  medicine_name_freetext?: string | null
  dosage?: string | null
  frequency?: string | null
  duration?: string | null
  route?: string | null
  prescribed_quantity: number
  instructions?: string | null
}

export interface PrescriptionCreateRequest {
  encounter_id: string
  items: PrescriptionItemCreateRequest[]
}

export interface PrescriptionItemSummary {
  id: string
  medicine_id: string | null
  medicine_name_freetext: string | null
  dosage: string | null
  frequency: string | null
  duration: string | null
  route: string | null
  prescribed_quantity: number
  dispensed_quantity: number
  instructions: string | null
}

export interface PrescriptionSummary {
  id: string
  tenant_id: string
  encounter_id: string
  doctor_id: string
  supersedes_prescription_id: string | null
  issued_at: string
  items: PrescriptionItemSummary[]
  pdf_document_id: string | null
  // Relative to the backend origin including /api/v1 — don't pass this
  // straight to apiClient (whose baseURL already includes /api/v1); build
  // the request path from pdf_document_id instead. See features/files/api.ts.
  pdf_download_url: string | null
}

export interface PrescriptionListResponse {
  items: PrescriptionSummary[]
  total: number
  limit: number
  offset: number
}

export interface PrescriptionSearchParams {
  encounterId?: string
  patientId?: string
  doctorId?: string
  limit?: number
  offset?: number
}
