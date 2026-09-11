import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { searchEncounters, searchQueue } from '@/features/checkin/api'
import { ACTIVE_QUEUE_STATUSES } from '@/features/checkin/types'
import { useAuth } from '@/features/auth/auth-context'
import { searchPatients } from '@/features/patients/api'
import { todayLocalRange, todayUTCDate } from '@/lib/date'

export interface DashboardMetric {
  value: number | undefined
  isLoading: boolean
  visible: boolean
}

// Every card is independently gated by the permission its own source
// endpoint requires — a caller missing one just doesn't see that card,
// same permission-driven-UI convention as the rest of this app. There is
// no single "dashboard summary" backend endpoint; each metric is derived
// from an existing search endpoint's `total` (or, for Doctors on Duty,
// computed client-side from one shared queue fetch — see
// features/opd/use-doctor-queue.ts for the same join-and-filter pattern
// applied to a single doctor instead of the whole tenant).
export function useDashboardMetrics() {
  const { hasPermission } = useAuth()
  const canViewPatients = hasPermission('patients.view_demographics')
  const canViewQueue = hasPermission('queue.view')
  const canViewEncounters = hasPermission('checkin.view')

  const patientsQuery = useQuery({
    queryKey: ['dashboard', 'patients-total'],
    queryFn: () => searchPatients({ limit: 1 }),
    enabled: canViewPatients,
    staleTime: 60_000,
  })

  const queueQuery = useQuery({
    queryKey: ['dashboard', 'queue-today'],
    queryFn: () => searchQueue({ limit: 100 }),
    enabled: canViewQueue,
    refetchInterval: 30_000,
  })

  const { start, end } = useMemo(() => todayLocalRange(), [])

  const footfallQuery = useQuery({
    queryKey: ['dashboard', 'footfall-today', start, end],
    queryFn: () => searchEncounters({ dateFrom: start, dateTo: end, limit: 1 }),
    enabled: canViewEncounters,
  })

  const completedQuery = useQuery({
    queryKey: ['dashboard', 'completed-today', start, end],
    queryFn: () => searchEncounters({ dateFrom: start, dateTo: end, status: 'COMPLETED', limit: 1 }),
    enabled: canViewEncounters,
  })

  // token_date is a UTC calendar date — see lib/date.ts::todayUTCDate's
  // own docstring for why this can't be todayLocalDate().
  const today = todayUTCDate()
  const activeTokens = useMemo(
    () =>
      (queueQuery.data?.items ?? []).filter(
        (t) => t.token_date === today && (ACTIVE_QUEUE_STATUSES as readonly string[]).includes(t.status),
      ),
    [queueQuery.data, today],
  )
  const doctorsOnDuty = useMemo(
    () => new Set(activeTokens.map((t) => t.doctor_id).filter((id): id is string => Boolean(id))).size,
    [activeTokens],
  )

  const registeredPatients: DashboardMetric = {
    value: patientsQuery.data?.total,
    isLoading: patientsQuery.isLoading,
    visible: canViewPatients,
  }
  const todaysFootfall: DashboardMetric = {
    value: footfallQuery.data?.total,
    isLoading: footfallQuery.isLoading,
    visible: canViewEncounters,
  }
  const completedConsultations: DashboardMetric = {
    value: completedQuery.data?.total,
    isLoading: completedQuery.isLoading,
    visible: canViewEncounters,
  }
  const doctorsOnDutyMetric: DashboardMetric = {
    value: canViewQueue ? doctorsOnDuty : undefined,
    isLoading: queueQuery.isLoading,
    visible: canViewQueue,
  }

  return { registeredPatients, todaysFootfall, completedConsultations, doctorsOnDuty: doctorsOnDutyMetric }
}
