import { useQuery } from '@tanstack/react-query'
import { listBranches } from '@/features/branches/api'

export function useBranches() {
  return useQuery({
    queryKey: ['branches'],
    queryFn: listBranches,
    staleTime: 5 * 60_000,
  })
}
