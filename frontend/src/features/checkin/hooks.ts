import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getEncounter, registerWalkIn } from '@/features/checkin/api'
import type { WalkInRequest } from '@/features/checkin/types'

export function useEncounter(encounterId: string | undefined) {
  return useQuery({
    queryKey: ['encounters', 'get', encounterId],
    queryFn: () => getEncounter(encounterId!),
    enabled: Boolean(encounterId),
  })
}

export function useRegisterWalkIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: WalkInRequest) => registerWalkIn(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}
