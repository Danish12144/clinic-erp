import { apiClient } from '@/lib/api-client'
import type { ClinicSummary, ClinicUpdateRequest, TenantSettingSummary } from '@/features/tenancy/types'

export async function getMyClinic(): Promise<ClinicSummary> {
  const { data } = await apiClient.get<ClinicSummary>('/clinics/me')
  return data
}

export async function updateMyClinic(payload: ClinicUpdateRequest): Promise<ClinicSummary> {
  const { data } = await apiClient.patch<ClinicSummary>('/clinics/me', payload)
  return data
}

export async function listClinicSettings(): Promise<TenantSettingSummary[]> {
  const { data } = await apiClient.get<TenantSettingSummary[]>('/clinics/me/settings')
  return data
}

export async function upsertClinicSetting(key: string, value: unknown): Promise<TenantSettingSummary> {
  const { data } = await apiClient.put<TenantSettingSummary>(`/clinics/me/settings/${encodeURIComponent(key)}`, { value })
  return data
}

export async function deleteClinicSetting(key: string): Promise<void> {
  await apiClient.delete(`/clinics/me/settings/${encodeURIComponent(key)}`)
}
