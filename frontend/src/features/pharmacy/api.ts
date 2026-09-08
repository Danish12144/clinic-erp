import { apiClient } from '@/lib/api-client'
import type { MedicineListResponse } from '@/features/pharmacy/types'

export async function searchMedicines(query: string): Promise<MedicineListResponse> {
  const { data } = await apiClient.get<MedicineListResponse>('/pharmacy/medicines', {
    params: { q: query || undefined, is_active: true, limit: 20 },
  })
  return data
}
