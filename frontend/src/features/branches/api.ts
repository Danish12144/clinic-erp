import { apiClient } from '@/lib/api-client'
import type { BranchSummary } from '@/features/branches/types'

export async function listBranches(): Promise<BranchSummary[]> {
  const { data } = await apiClient.get<BranchSummary[]>('/branches')
  return data
}
