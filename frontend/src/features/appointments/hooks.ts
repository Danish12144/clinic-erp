import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  cancelAppointment,
  cancelMyAppointment,
  createAppointment,
  createMyAppointment,
  getMyAppointments,
  rescheduleAppointment,
  rescheduleMyAppointment,
  searchAppointments,
} from '@/features/appointments/api'
import type {
  AppointmentCancelRequest,
  AppointmentCreateRequest,
  AppointmentRescheduleRequest,
  AppointmentSearchParams,
  MyAppointmentCreateRequest,
} from '@/features/appointments/types'

export function useAppointmentSearch(params: AppointmentSearchParams) {
  return useQuery({
    queryKey: ['appointments', 'search', params],
    queryFn: () => searchAppointments(params),
    enabled: Boolean(params.doctorId && params.dateFrom && params.dateTo),
  })
}

function useInvalidateAppointments() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['appointments'] })
}

export function useCreateAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: (payload: AppointmentCreateRequest) => createAppointment(payload),
    onSuccess: invalidate,
  })
}

export function useRescheduleAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: string; payload: AppointmentRescheduleRequest }) =>
      rescheduleAppointment(appointmentId, payload),
    onSuccess: invalidate,
  })
}

export function useCancelAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: string; payload: AppointmentCancelRequest }) =>
      cancelAppointment(appointmentId, payload),
    onSuccess: invalidate,
  })
}

// ---- Patient portal (self-booking) ---------------------------------------

export function useMyAppointments() {
  return useQuery({
    queryKey: ['appointments', 'me'],
    queryFn: () => getMyAppointments({}),
  })
}

export function useCreateMyAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: (payload: MyAppointmentCreateRequest) => createMyAppointment(payload),
    onSuccess: invalidate,
  })
}

export function useRescheduleMyAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: string; payload: AppointmentRescheduleRequest }) =>
      rescheduleMyAppointment(appointmentId, payload),
    onSuccess: invalidate,
  })
}

export function useCancelMyAppointment() {
  const invalidate = useInvalidateAppointments()
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: string; payload: AppointmentCancelRequest }) =>
      cancelMyAppointment(appointmentId, payload),
    onSuccess: invalidate,
  })
}
