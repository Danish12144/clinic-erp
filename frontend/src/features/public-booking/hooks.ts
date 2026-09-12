import { useMutation, useQuery } from '@tanstack/react-query'
import {
  bookPublicAppointment,
  getPublicClinic,
  listPublicBranches,
  listPublicDoctors,
  listPublicSlots,
  retryPublicPayment,
} from '@/features/public-booking/api'
import type { PublicBookingRequest, PublicRetryPaymentRequest } from '@/features/public-booking/types'

export function usePublicClinic(clinicSlug: string | undefined) {
  return useQuery({
    queryKey: ['public-booking', 'clinic', clinicSlug],
    queryFn: () => getPublicClinic(clinicSlug!),
    enabled: Boolean(clinicSlug),
    retry: false,
  })
}

export function usePublicBranches(clinicSlug: string | undefined) {
  return useQuery({
    queryKey: ['public-booking', 'branches', clinicSlug],
    queryFn: () => listPublicBranches(clinicSlug!),
    enabled: Boolean(clinicSlug),
  })
}

export function usePublicDoctors(clinicSlug: string | undefined, branchId: string | undefined) {
  return useQuery({
    queryKey: ['public-booking', 'doctors', clinicSlug, branchId],
    queryFn: () => listPublicDoctors(clinicSlug!, branchId),
    enabled: Boolean(clinicSlug),
  })
}

export function usePublicSlots(clinicSlug: string | undefined, doctorId: string | undefined, on: string | undefined) {
  return useQuery({
    queryKey: ['public-booking', 'slots', clinicSlug, doctorId, on],
    queryFn: () => listPublicSlots(clinicSlug!, doctorId!, on!),
    enabled: Boolean(clinicSlug) && Boolean(doctorId) && Boolean(on),
  })
}

export function useBookPublicAppointment(clinicSlug: string) {
  return useMutation({
    mutationFn: (payload: PublicBookingRequest) => bookPublicAppointment(clinicSlug, payload),
  })
}

export function useRetryPublicPayment(clinicSlug: string) {
  return useMutation({
    mutationFn: ({ appointmentId, payload }: { appointmentId: string; payload: PublicRetryPaymentRequest }) =>
      retryPublicPayment(clinicSlug, appointmentId, payload),
  })
}
