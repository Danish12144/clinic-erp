import { apiClient } from '@/lib/api-client'
import type {
  AppointmentCancelRequest,
  AppointmentCreateRequest,
  AppointmentListResponse,
  AppointmentRescheduleRequest,
  AppointmentSearchParams,
  AppointmentSummary,
  MyAppointmentCreateRequest,
} from '@/features/appointments/types'

export async function searchAppointments(params: AppointmentSearchParams): Promise<AppointmentListResponse> {
  const { data } = await apiClient.get<AppointmentListResponse>('/appointments', {
    params: {
      patient_id: params.patientId || undefined,
      doctor_id: params.doctorId || undefined,
      branch_id: params.branchId || undefined,
      status: params.status || undefined,
      date_from: params.dateFrom || undefined,
      date_to: params.dateTo || undefined,
      limit: params.limit ?? 100,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function createAppointment(payload: AppointmentCreateRequest): Promise<AppointmentSummary> {
  const { data } = await apiClient.post<AppointmentSummary>('/appointments', payload)
  return data
}

export async function rescheduleAppointment(
  appointmentId: string,
  payload: AppointmentRescheduleRequest,
): Promise<AppointmentSummary> {
  const { data } = await apiClient.patch<AppointmentSummary>(`/appointments/${appointmentId}`, payload)
  return data
}

export async function cancelAppointment(appointmentId: string, payload: AppointmentCancelRequest): Promise<AppointmentSummary> {
  const { data } = await apiClient.post<AppointmentSummary>(`/appointments/${appointmentId}/cancel`, payload)
  return data
}

// ---- Patient portal (self-booking, /appointments/me) --------------------

export async function getMyAppointments(params: { limit?: number; offset?: number }): Promise<AppointmentListResponse> {
  const { data } = await apiClient.get<AppointmentListResponse>('/appointments/me', {
    params: { limit: params.limit ?? 50, offset: params.offset ?? 0 },
  })
  return data
}

export async function createMyAppointment(payload: MyAppointmentCreateRequest): Promise<AppointmentSummary> {
  const { data } = await apiClient.post<AppointmentSummary>('/appointments/me', payload)
  return data
}

export async function rescheduleMyAppointment(
  appointmentId: string,
  payload: AppointmentRescheduleRequest,
): Promise<AppointmentSummary> {
  const { data } = await apiClient.patch<AppointmentSummary>(`/appointments/me/${appointmentId}`, payload)
  return data
}

export async function cancelMyAppointment(appointmentId: string, payload: AppointmentCancelRequest): Promise<AppointmentSummary> {
  const { data } = await apiClient.post<AppointmentSummary>(`/appointments/me/${appointmentId}/cancel`, payload)
  return data
}
