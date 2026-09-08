import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listVitalsForEncounter, recordVitals } from '@/features/vitals/api'
import type { VitalsCreateRequest } from '@/features/vitals/types'

export function useEncounterVitals(encounterId: string | undefined) {
  return useQuery({
    queryKey: ['vitals', 'by-encounter', encounterId],
    queryFn: () => listVitalsForEncounter(encounterId!),
    enabled: Boolean(encounterId),
  })
}

export function useRecordVitals() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: VitalsCreateRequest) => recordVitals(payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['vitals', 'by-encounter', variables.encounter_id] })
    },
  })
}
