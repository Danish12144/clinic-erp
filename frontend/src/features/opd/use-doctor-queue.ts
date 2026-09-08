import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { getEncounter } from '@/features/checkin/api'
import { ACTIVE_QUEUE_STATUSES } from '@/features/checkin/types'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'
import type { EncounterSummary, QueueTokenSummary } from '@/features/checkin/types'
import { searchQueue } from '@/features/checkin/api'
import { todayLocalDate } from '@/lib/date'

export interface OpdQueueRow {
  token: QueueTokenSummary
  encounter: EncounterSummary | undefined
  patient: PatientSummary | undefined
  isLoadingDetail: boolean
}

const POLL_INTERVAL_MS = 15_000

// There's no single backend endpoint that returns "today's queue with
// patient names" — QueueTokenSummary only has encounter_id, and
// EncounterSummary only has patient_id (see backend/app/modules/checkin/
// schemas.py). This hook joins queue -> encounter -> patient client-side,
// each level fetched in parallel via useQueries, bounded by one doctor's
// realistically-small daily queue size.
export function useDoctorOpdQueue(doctorId: string | undefined) {
  const queueQuery = useQuery({
    queryKey: ['queue', 'doctor', doctorId],
    queryFn: () => searchQueue({ doctorId }),
    enabled: Boolean(doctorId),
    refetchInterval: POLL_INTERVAL_MS,
  })

  const today = todayLocalDate()
  const activeTokens = useMemo(
    () =>
      (queueQuery.data?.items ?? [])
        .filter((t) => t.token_date === today && (ACTIVE_QUEUE_STATUSES as readonly string[]).includes(t.status))
        .sort((a, b) => a.token_number - b.token_number),
    [queueQuery.data, today],
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

  const rows: OpdQueueRow[] = activeTokens.map((token, index) => {
    const encounterQuery = encounterQueries[index]
    const encounter = encounterQuery?.data
    const patient = encounter ? patientsById.get(encounter.patient_id) : undefined
    return {
      token,
      encounter,
      patient,
      isLoadingDetail: Boolean(encounterQuery?.isLoading) || (Boolean(encounter) && !patient),
    }
  })

  return {
    rows,
    isLoading: queueQuery.isLoading,
    isFetching: queueQuery.isFetching,
    refetch: queueQuery.refetch,
  }
}
