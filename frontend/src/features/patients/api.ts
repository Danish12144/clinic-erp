import { apiClient } from '@/lib/api-client'
import type {
  PatientCreateRequest,
  PatientCreateResponse,
  PatientListResponse,
  PatientSearchParams,
  PatientSummary,
} from '@/features/patients/types'

export async function getPatient(patientId: string): Promise<PatientSummary> {
  const { data } = await apiClient.get<PatientSummary>(`/patients/${patientId}`)
  return data
}

// Patient-portal only — resolves the logged-in PATIENT's own record.
// Staff calling this would 403 (GET /patients/me is patient-scoped
// server-side), so no caller outside the portal needs it.
export async function getMyPatient(): Promise<PatientSummary> {
  const { data } = await apiClient.get<PatientSummary>('/patients/me')
  return data
}

export async function searchPatients(params: PatientSearchParams): Promise<PatientListResponse> {
  const { data } = await apiClient.get<PatientListResponse>('/patients', {
    params: {
      q: params.q || undefined,
      phone: params.phone || undefined,
      mrn: params.mrn || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function createPatient(payload: PatientCreateRequest): Promise<PatientCreateResponse> {
  const { data } = await apiClient.post<PatientCreateResponse>('/patients', payload)
  return data
}
