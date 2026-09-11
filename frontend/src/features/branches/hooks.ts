import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createBranch, listBranches, updateBranch } from '@/features/branches/api'
import type { BranchCreateRequest, BranchUpdateRequest } from '@/features/branches/types'

export function useBranches() {
  return useQuery({
    queryKey: ['branches'],
    queryFn: listBranches,
    staleTime: 5 * 60_000,
  })
}

export function useCreateBranch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: BranchCreateRequest) => createBranch(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['branches'] }),
  })
}

export function useUpdateBranch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ branchId, payload }: { branchId: string; payload: BranchUpdateRequest }) => updateBranch(branchId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['branches'] }),
  })
}
