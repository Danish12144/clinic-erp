import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deletePermissionOverride, searchPermissionOverrides, setPermissionOverride } from '@/features/permissions/api'
import type { PermissionOverrideSetRequest } from '@/features/permissions/types'

const KEY = ['permission-overrides']

export function usePermissionOverrides() {
  return useQuery({ queryKey: KEY, queryFn: searchPermissionOverrides })
}

export function useSetPermissionOverride() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: PermissionOverrideSetRequest) => setPermissionOverride(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeletePermissionOverride() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (overrideId: string) => deletePermissionOverride(overrideId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  })
}
