import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  completeConsultation,
  issuePrescription,
  searchConsultationsByEncounter,
  searchPrescriptions,
  startConsultation,
  updateConsultation,
} from '@/features/consultations/api'
import type {
  ConsultationStartRequest,
  ConsultationUpdateRequest,
  PrescriptionCreateRequest,
} from '@/features/consultations/types'

export function usePatientPrescriptions(patientId: string | undefined) {
  return useQuery({
    queryKey: ['prescriptions', 'by-patient', patientId],
    queryFn: () => searchPrescriptions({ patientId, limit: 20 }),
    enabled: Boolean(patientId),
  })
}

// Used by the "completed encounter" screen to offer a persistent Print/
// Download button — the PrescriptionPreviewDialog shown right after
// finishing a consultation can be unmounted before it's interacted with
// (a completed-encounter refetch swaps the whole workspace to the
// read-only "this encounter is completed" view mid-fetch), so this is the
// reliable fallback: look the prescription back up by encounter_id rather
// than depending on that transient dialog having stayed mounted.
export function usePrescriptionsByEncounter(encounterId: string | undefined) {
  return useQuery({
    queryKey: ['prescriptions', 'by-encounter', encounterId],
    queryFn: () => searchPrescriptions({ encounterId, limit: 5 }),
    enabled: Boolean(encounterId),
  })
}

export function useConsultationByEncounter(encounterId: string | undefined) {
  return useQuery({
    queryKey: ['consultations', 'by-encounter', encounterId],
    queryFn: () => searchConsultationsByEncounter(encounterId!),
    enabled: Boolean(encounterId),
    select: (data) => data.items[0] ?? null,
  })
}

export function useStartConsultation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ConsultationStartRequest) => startConsultation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['consultations'] })
      void queryClient.invalidateQueries({ queryKey: ['encounters'] })
    },
  })
}

export function useUpdateConsultation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ consultationId, payload }: { consultationId: string; payload: ConsultationUpdateRequest }) =>
      updateConsultation(consultationId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['consultations'] })
    },
  })
}

export function useCompleteConsultation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (consultationId: string) => completeConsultation(consultationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['consultations'] })
      void queryClient.invalidateQueries({ queryKey: ['encounters'] })
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}

export function useIssuePrescription() {
  return useMutation({
    mutationFn: (payload: PrescriptionCreateRequest) => issuePrescription(payload),
  })
}
