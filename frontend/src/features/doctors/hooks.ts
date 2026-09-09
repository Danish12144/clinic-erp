import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createDoctor, listDoctorDirectory, listDoctors } from '@/features/doctors/api'
import { useAuth } from '@/features/auth/auth-context'
import type { DoctorCreateRequest, WorkingHours } from '@/features/doctors/types'

export interface BookableDoctor {
  userId: string
  name: string
  specialization: string | null
  workingHours: WorkingHours
  branchIds: string[]
}

// Unifies the two doctor-listing endpoints into one shape for booking UIs:
// doctors.view_directory (Receptionist/Patient — the endpoint the backend
// actually designed for this) when held, else falling back to the
// Owner-only staff.manage admin list filtered to ACTIVE doctors — Owner
// does not hold doctors.view_directory (see features/doctors/api.ts).
// Same graceful-multi-path pattern NewPatientDialog already established.
export function useBookableDoctors() {
  const { hasPermission } = useAuth()
  const canUseDirectory = hasPermission('doctors.view_directory')
  const canUseAdminList = hasPermission('staff.manage')

  const directoryQuery = useDoctorDirectory()
  const adminListQuery = useDoctors({ includeInactive: false })

  const doctors = useMemo<BookableDoctor[]>(() => {
    if (canUseDirectory && directoryQuery.data) {
      return directoryQuery.data.items.map((d) => ({
        userId: d.user_id,
        name: [d.first_name, d.last_name].filter(Boolean).join(' ') || 'Unnamed doctor',
        specialization: d.specialization,
        workingHours: d.working_hours,
        branchIds: d.branch_ids,
      }))
    }
    if (canUseAdminList && adminListQuery.data) {
      return adminListQuery.data.items
        .filter((d) => d.status === 'ACTIVE')
        .map((d) => ({
          userId: d.user_id,
          name: [d.first_name, d.last_name].filter(Boolean).join(' ') || 'Unnamed doctor',
          specialization: d.specialization,
          workingHours: d.working_hours,
          branchIds: d.branch_ids,
        }))
    }
    return []
  }, [canUseDirectory, directoryQuery.data, canUseAdminList, adminListQuery.data])

  return {
    doctors,
    isLoading: canUseDirectory ? directoryQuery.isLoading : adminListQuery.isLoading,
  }
}

export function useDoctorDirectory() {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['doctors', 'directory'],
    queryFn: listDoctorDirectory,
    enabled: hasPermission('doctors.view_directory'),
    staleTime: 60_000,
  })
}

// Self-gates by staff.manage (Owner-only) — earlier callers (Staff
// Directory) only ever ran this behind an already-Owner-gated route, but
// useBookableDoctors below calls it unconditionally regardless of role, so
// the gate has to live here now rather than being assumed by the caller.
export function useDoctors(params: { q?: string; includeInactive?: boolean }) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['doctors', 'list', params],
    queryFn: () => listDoctors(params),
    enabled: hasPermission('staff.manage'),
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
