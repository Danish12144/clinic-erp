import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createStaff, listStaff } from '@/features/staff/api'
import type { StaffCreateRequest } from '@/features/staff/types'

export function useStaff(params: { q?: string; includeInactive?: boolean }) {
  return useQuery({
    queryKey: ['staff', 'list', params],
    queryFn: () => listStaff(params),
    staleTime: 30_000,
  })
}

export function useCreateStaff() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: StaffCreateRequest) => createStaff(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['staff', 'list'] })
    },
  })
}
