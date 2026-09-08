import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createDoctor, listDoctorDirectory, listDoctors } from '@/features/doctors/api'
import { useAuth } from '@/features/auth/auth-context'
import type { DoctorCreateRequest } from '@/features/doctors/types'

export function useDoctorDirectory() {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['doctors', 'directory'],
    queryFn: listDoctorDirectory,
    enabled: hasPermission('doctors.view_directory'),
    staleTime: 60_000,
  })
}

export function useDoctors(params: { q?: string; includeInactive?: boolean }) {
  return useQuery({
    queryKey: ['doctors', 'list', params],
    queryFn: () => listDoctors(params),
    staleTime: 30_000,
  })
}

export function useCreateDoctor() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: DoctorCreateRequest) => createDoctor(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['doctors', 'list'] })
    },
  })
}
