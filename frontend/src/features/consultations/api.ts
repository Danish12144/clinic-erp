import { apiClient } from '@/lib/api-client'
import type {
  ConsultationListResponse,
  ConsultationStartRequest,
  ConsultationSummary,
  ConsultationUpdateRequest,
  PrescriptionCreateRequest,
  PrescriptionListResponse,
  PrescriptionSearchParams,
  PrescriptionSummary,
} from '@/features/consultations/types'

export async function searchPrescriptions(params: PrescriptionSearchParams): Promise<PrescriptionListResponse> {
  const { data } = await apiClient.get<PrescriptionListResponse>('/prescriptions', {
    params: {
      encounter_id: params.encounterId || undefined,
      patient_id: params.patientId || undefined,
      doctor_id: params.doctorId || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function startConsultation(payload: ConsultationStartRequest): Promise<ConsultationSummary> {
  const { data } = await apiClient.post<ConsultationSummary>('/consultations', payload)
  return data
}

export async function searchConsultationsByEncounter(encounterId: string): Promise<ConsultationListResponse> {
  const { data } = await apiClient.get<ConsultationListResponse>('/consultations', { params: { encounter_id: encounterId } })
  return data
}

export async function updateConsultation(
  consultationId: string,
  payload: ConsultationUpdateRequest,
): Promise<ConsultationSummary> {
  const { data } = await apiClient.patch<ConsultationSummary>(`/consultations/${consultationId}`, payload)
  return data
}

export async function completeConsultation(consultationId: string): Promise<ConsultationSummary> {
  const { data } = await apiClient.post<ConsultationSummary>(`/consultations/${consultationId}/complete`)
  return data
}

export async function issuePrescription(payload: PrescriptionCreateRequest): Promise<PrescriptionSummary> {
  const { data } = await apiClient.post<PrescriptionSummary>('/prescriptions', payload)
  return data
}
