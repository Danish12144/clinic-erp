import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/auth-context'
import { searchPatients } from '@/features/patients/api'

// GET /patients with no q/phone/mrn filter orders by created_at desc
// (backend/app/modules/patients/repository.py) — the first `limit` rows
// already are "most recently registered," no extra sort needed.
export function useRecentRegistrations(limit = 5) {
  const { hasPermission } = useAuth()
  const enabled = hasPermission('patients.view_demographics')

  const query = useQuery({
    queryKey: ['dashboard', 'recent-registrations', limit],
    queryFn: () => searchPatients({ limit }),
    enabled,
  })

  return { rows: query.data?.items ?? [], isLoading: query.isLoading, enabled }
}
