import { apiClient } from '@/lib/api-client'
import type { PatientEmrTimeline } from '@/features/emr/types'

export async function getPatientEmrTimeline(patientId: string): Promise<PatientEmrTimeline> {
  const { data } = await apiClient.get<PatientEmrTimeline>(`/patients/${patientId}/emr`, { params: { limit: 100 } })
  return data
}
