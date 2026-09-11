import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { getEncounter, searchQueue } from '@/features/checkin/api'
import { ACTIVE_QUEUE_STATUSES } from '@/features/checkin/types'
import type { QueueTokenSummary } from '@/features/checkin/types'
import { useAuth } from '@/features/auth/auth-context'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'
import { todayUTCDate } from '@/lib/date'

export interface LiveQueueRow {
  token: QueueTokenSummary
  patient: PatientSummary | undefined
}

// Tenant-wide equivalent of features/opd/use-doctor-queue.ts's join
// (queue -> encounter -> patient, no single backend endpoint returns this
// pre-joined) — this one has no doctor_id filter, since a dashboard
// snapshot is a front-desk/owner view of the whole clinic's queue, not one
// doctor's. Capped to `limit` rows (default 6) since it's a glance widget,
// not the full queue — see pages/opd-queue-page.tsx for the full list.
export function useLiveQueueSnapshot(limit = 6) {
  const { hasPermission } = useAuth()
  const enabled = hasPermission('queue.view')

  const queueQuery = useQuery({
    queryKey: ['dashboard', 'queue-snapshot'],
    queryFn: () => searchQueue({ limit: 100 }),
    enabled,
    refetchInterval: 30_000,
  })

  // token_date is a UTC calendar date — see lib/date.ts::todayUTCDate's
  // own docstring for why this can't be todayLocalDate().
  const today = todayUTCDate()
  const activeTokens = useMemo(
    () =>
      (queueQuery.data?.items ?? [])
        .filter((t) => t.token_date === today && (ACTIVE_QUEUE_STATUSES as readonly string[]).includes(t.status))
        .sort((a, b) => a.token_number - b.token_number)
        .slice(0, limit),
    [queueQuery.data, today, limit],
  )

  const encounterQueries = useQueries({
    queries: activeTokens.map((token) => ({
      queryKey: ['encounters', 'get', token.encounter_id],
      queryFn: () => getEncounter(token.encounter_id),
      staleTime: 10_000,
    })),
  })

  const patientIds = useMemo(() => {
    const ids = new Set<string>()
    for (const q of encounterQueries) {
      if (q.data) ids.add(q.data.patient_id)
    }
    return Array.from(ids)
  }, [encounterQueries])

  const patientQueries = useQueries({
    queries: patientIds.map((id) => ({
      queryKey: ['patients', 'get', id],
      queryFn: () => getPatient(id),
      staleTime: 60_000,
    })),
  })

  const patientsById = useMemo(() => {
    const map = new Map<string, PatientSummary>()
    for (const q of patientQueries) {
      if (q.data) map.set(q.data.id, q.data)
    }
    return map
  }, [patientQueries])

  const rows: LiveQueueRow[] = activeTokens.map((token, index) => {
    const encounter = encounterQueries[index]?.data
    return { token, patient: encounter ? patientsById.get(encounter.patient_id) : undefined }
  })

  return { rows, isLoading: queueQuery.isLoading, enabled }
}
