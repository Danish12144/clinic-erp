import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelAppointment, createAppointment, rescheduleAppointment, searchAppointments } from '@/features/appointments/api'
import type {
  AppointmentCancelRequest,
  AppointmentCreateRequest,
  AppointmentRescheduleRequest,
  AppointmentSearchParams,
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
