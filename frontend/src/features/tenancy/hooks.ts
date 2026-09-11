import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteClinicSetting, getMyClinic, listClinicSettings, updateMyClinic, upsertClinicSetting } from '@/features/tenancy/api'
import type { ClinicUpdateRequest } from '@/features/tenancy/types'

export function useMyClinic() {
  return useQuery({ queryKey: ['clinic', 'me'], queryFn: getMyClinic })
}

export function useClinicSettings() {
  return useQuery({ queryKey: ['clinic', 'settings'], queryFn: listClinicSettings })
}

export function useUpdateClinic() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ClinicUpdateRequest) => updateMyClinic(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['clinic', 'me'] }),
  })
}

export function useUpsertClinicSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => upsertClinicSetting(key, value),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['clinic', 'settings'] }),
  })
}

export function useDeleteClinicSetting() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => deleteClinicSetting(key),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['clinic', 'settings'] }),
  })
}
