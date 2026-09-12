import { apiClient } from '@/lib/api-client'
import type {
  PublicBookingRequest,
  PublicBookingResponse,
  PublicBranchSummary,
  PublicClinicSummary,
  PublicDoctorSummary,
  PublicGatewayOrderInfo,
  PublicRetryPaymentRequest,
  PublicSlotsResponse,
} from '@/features/public-booking/types'

// No auth header is ever attached to these — apiClient only attaches one
// when a session exists (see lib/api-client.ts), and a guest booking a
// slot has none.

export async function getPublicClinic(clinicSlug: string): Promise<PublicClinicSummary> {
  const { data } = await apiClient.get<PublicClinicSummary>(`/public/clinics/${clinicSlug}`)
  return data
}

export async function listPublicBranches(clinicSlug: string): Promise<PublicBranchSummary[]> {
  const { data } = await apiClient.get<PublicBranchSummary[]>(`/public/clinics/${clinicSlug}/branches`)
  return data
}

export async function listPublicDoctors(clinicSlug: string, branchId?: string): Promise<PublicDoctorSummary[]> {
  const { data } = await apiClient.get<PublicDoctorSummary[]>(`/public/clinics/${clinicSlug}/doctors`, {
    params: { branch_id: branchId || undefined },
  })
  return data
}

export async function listPublicSlots(clinicSlug: string, doctorId: string, on: string): Promise<PublicSlotsResponse> {
  const { data } = await apiClient.get<PublicSlotsResponse>(`/public/clinics/${clinicSlug}/doctors/${doctorId}/slots`, {
    params: { on },
  })
  return data
}

export async function bookPublicAppointment(clinicSlug: string, payload: PublicBookingRequest): Promise<PublicBookingResponse> {
  const { data } = await apiClient.post<PublicBookingResponse>(`/public/clinics/${clinicSlug}/book`, payload)
  return data
}

export async function retryPublicPayment(
  clinicSlug: string, appointmentId: string, payload: PublicRetryPaymentRequest,
): Promise<PublicGatewayOrderInfo> {
  const { data } = await apiClient.post<PublicGatewayOrderInfo>(
    `/public/clinics/${clinicSlug}/appointments/${appointmentId}/retry-payment`, payload,
  )
  return data
}
