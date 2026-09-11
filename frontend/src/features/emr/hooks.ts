import { useQuery } from '@tanstack/react-query'
import { getPatientEmrTimeline } from '@/features/emr/api'

export function usePatientEmrTimeline(patientId: string | undefined) {
  return useQuery({
    queryKey: ['emr', 'timeline', patientId],
    queryFn: () => getPatientEmrTimeline(patientId!),
    enabled: Boolean(patientId),
  })
}
