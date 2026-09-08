import { useQueries, useQuery } from '@tanstack/react-query'
import { searchEncounters } from '@/features/checkin/api'
import type { EncounterSummary } from '@/features/checkin/types'
import { useAuth } from '@/features/auth/auth-context'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'

export interface RecentActivityRow {
  encounter: EncounterSummary
  patient: PatientSummary | undefined
}

// GET /encounters orders by checked_in_at desc with no params
// (backend/app/modules/checkin/repository.py) — the first `limit` rows
// already are "most recent," no extra sort needed. Patient names are
// joined client-side the same way features/opd/use-doctor-queue.ts does.
export function useRecentActivity(limit = 5) {
  const { hasPermission } = useAuth()
  const enabled = hasPermission('checkin.view')

  const encountersQuery = useQuery({
    queryKey: ['dashboard', 'recent-encounters', limit],
    queryFn: () => searchEncounters({ limit }),
    enabled,
  })
  const encounters = encountersQuery.data?.items ?? []

  const patientQueries = useQueries({
    queries: encounters.map((encounter) => ({
      queryKey: ['patients', 'get', encounter.patient_id],
      queryFn: () => getPatient(encounter.patient_id),
      staleTime: 60_000,
    })),
  })

  const rows: RecentActivityRow[] = encounters.map((encounter, index) => ({
    encounter,
    patient: patientQueries[index]?.data,
  }))

  return { rows, isLoading: encountersQuery.isLoading, enabled }
}
