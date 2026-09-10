import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createPatient, getMyPatient, getPatient, searchPatients } from '@/features/patients/api'
import { classifyPatientSearchTerm } from '@/features/patients/search-classifier'
import { useDebouncedValue } from '@/lib/use-debounced-value'
import type { PatientCreateRequest } from '@/features/patients/types'

export function usePatient(patientId: string | undefined) {
  return useQuery({
    queryKey: ['patients', 'get', patientId],
    queryFn: () => getPatient(patientId!),
    enabled: Boolean(patientId),
  })
}

// Patient-portal only — see getMyPatient's own comment.
export function useMyPatient() {
  return useQuery({ queryKey: ['patients', 'me'], queryFn: getMyPatient })
}

// Debounced, live patient search — an empty term browses the most
// recently registered patients (the backend's own default ordering when
// no filter is supplied), so the screen never shows a blank state.
export function usePatientSearch(rawTerm: string) {
  const debouncedTerm = useDebouncedValue(rawTerm, 350)
  const classified = classifyPatientSearchTerm(debouncedTerm)

  return useQuery({
    queryKey: ['patients', 'search', classified],
    queryFn: () => searchPatients(classified ? { [classified.field]: classified.value } : {}),
    placeholderData: keepPreviousData,
  })
}

export function useCreatePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PatientCreateRequest) => createPatient(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['patients', 'search'] })
    },
  })
}
