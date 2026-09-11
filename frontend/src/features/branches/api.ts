import { apiClient } from '@/lib/api-client'
import type { BranchCreateRequest, BranchSummary, BranchUpdateRequest } from '@/features/branches/types'

export async function listBranches(): Promise<BranchSummary[]> {
  const { data } = await apiClient.get<BranchSummary[]>('/branches')
  return data
}

export async function createBranch(payload: BranchCreateRequest): Promise<BranchSummary> {
  const { data } = await apiClient.post<BranchSummary>('/branches', payload)
  return data
}

export async function updateBranch(branchId: string, payload: BranchUpdateRequest): Promise<BranchSummary> {
  const { data } = await apiClient.patch<BranchSummary>(`/branches/${branchId}`, payload)
  return data
}
