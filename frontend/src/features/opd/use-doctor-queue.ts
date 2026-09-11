import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { getEncounter } from '@/features/checkin/api'
import { ACTIVE_QUEUE_STATUSES } from '@/features/checkin/types'
import { getPatient } from '@/features/patients/api'
import type { PatientSummary } from '@/features/patients/types'
import type { EncounterSummary, QueueTokenSummary } from '@/features/checkin/types'
import { searchQueue } from '@/features/checkin/api'
import { todayUTCDate } from '@/lib/date'

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
//
// `doctorId` is deliberately optional at the query level, not just at the
// type level — omitting it (rather than "not ready yet") is exactly what
// a Nurse's own use of this same page needs: Nurse holds vitals.record
// but not consultation.manage, has no "own" queue the way a Doctor does,
// and needs the whole branch's active queue to find patients waiting for
// a vitals reading before the doctor sees them. OpdQueuePage decides
// which case it's in and passes accordingly — this hook just needs to
// not gate fetching on doctorId being present.
export function useDoctorOpdQueue(doctorId: string | undefined) {
  const queueQuery = useQuery({
    queryKey: ['queue', 'doctor', doctorId],
    queryFn: () => searchQueue({ doctorId }),
    refetchInterval: POLL_INTERVAL_MS,
  })

  // token_date is a UTC calendar date (see todayUTCDate's own docstring for
  // why this can't be todayLocalDate() — a real bug this exact mismatch
  // caused, caught by e2e/collect-fee.spec.ts).
  const today = todayUTCDate()
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
