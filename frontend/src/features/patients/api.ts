import { apiClient } from '@/lib/api-client'
import type {
  PatientCreateRequest,
  PatientCreateResponse,
  PatientListResponse,
  PatientSearchParams,
} from '@/features/patients/types'

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
