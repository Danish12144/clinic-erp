import { apiClient } from '@/lib/api-client'
import type {
  DoctorCreateRequest,
  DoctorCreateResponse,
  DoctorDirectoryResponse,
  DoctorListResponse,
} from '@/features/doctors/types'

// Read-only, PII-minimal listing — only ACTIVE doctors, gated by
// doctors.view_directory (Receptionist/Patient only; Owner does NOT hold
// this permission — see backend/app/modules/doctors/router.py). Callers
// must check hasPermission('doctors.view_directory') before using this.
export async function listDoctorDirectory(): Promise<DoctorDirectoryResponse> {
  const { data } = await apiClient.get<DoctorDirectoryResponse>('/doctors/directory', { params: { limit: 100 } })
  return data
}

// Owner-only management view (staff.manage) — full PII, active + inactive.
export async function listDoctors(params: { q?: string; includeInactive?: boolean }): Promise<DoctorListResponse> {
  const { data } = await apiClient.get<DoctorListResponse>('/doctors', {
    params: { q: params.q || undefined, include_inactive: params.includeInactive ?? false, limit: 100 },
  })
  return data
}

export async function createDoctor(payload: DoctorCreateRequest): Promise<DoctorCreateResponse> {
  const { data } = await apiClient.post<DoctorCreateResponse>('/doctors', payload)
  return data
}
