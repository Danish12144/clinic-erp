import { useMutation, useQueryClient } from '@tanstack/react-query'
import { registerWalkIn } from '@/features/checkin/api'
import type { WalkInRequest } from '@/features/checkin/types'

export function useRegisterWalkIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: WalkInRequest) => registerWalkIn(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['queue'] })
    },
  })
}
