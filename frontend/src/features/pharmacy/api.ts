import { apiClient } from '@/lib/api-client'
import type {
  DispenseRequest,
  DispenseResult,
  MedicineBatchListResponse,
  MedicineBatchSummary,
  MedicineCreateRequest,
  MedicineListResponse,
  MedicineSearchParams,
  MedicineSummary,
  MedicineUpdateRequest,
  OTCSaleCreateRequest,
  ReceiveStockRequest,
  SaleListResponse,
  SaleSearchParams,
  SaleSummary,
} from '@/features/pharmacy/types'

// Kept for the Rx pad's lightweight autocomplete (features/opd's RxTable) —
// a narrower call shape than the full catalog search below.
export async function searchMedicines(query: string): Promise<MedicineListResponse> {
  const { data } = await apiClient.get<MedicineListResponse>('/pharmacy/medicines', {
    params: { q: query || undefined, is_active: true, limit: 20 },
  })
  return data
}

export async function searchMedicinesFull(params: MedicineSearchParams): Promise<MedicineListResponse> {
  const { data } = await apiClient.get<MedicineListResponse>('/pharmacy/medicines', {
    params: {
      q: params.q || undefined,
      category: params.category || undefined,
      is_active: params.isActive,
      low_stock_only: params.lowStockOnly ?? false,
      limit: params.limit ?? 30,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getMedicine(medicineId: string): Promise<MedicineSummary> {
  const { data } = await apiClient.get<MedicineSummary>(`/pharmacy/medicines/${medicineId}`)
  return data
}

export async function createMedicine(payload: MedicineCreateRequest): Promise<MedicineSummary> {
  const { data } = await apiClient.post<MedicineSummary>('/pharmacy/medicines', payload)
  return data
}

export async function updateMedicine(medicineId: string, payload: MedicineUpdateRequest): Promise<MedicineSummary> {
  const { data } = await apiClient.patch<MedicineSummary>(`/pharmacy/medicines/${medicineId}`, payload)
  return data
}

export async function receiveStock(medicineId: string, payload: ReceiveStockRequest): Promise<MedicineBatchSummary> {
  const { data } = await apiClient.post<MedicineBatchSummary>(`/pharmacy/medicines/${medicineId}/batches`, payload)
  return data
}

export async function searchMedicineBatches(medicineId: string): Promise<MedicineBatchListResponse> {
  const { data } = await apiClient.get<MedicineBatchListResponse>(`/pharmacy/medicines/${medicineId}/batches`, {
    params: { limit: 50 },
  })
  return data
}

export async function dispensePrescriptionItem(payload: DispenseRequest): Promise<DispenseResult> {
  const { data } = await apiClient.post<DispenseResult>('/pharmacy/dispense', payload)
  return data
}

export async function checkoutOtcSale(payload: OTCSaleCreateRequest): Promise<SaleSummary> {
  const { data } = await apiClient.post<SaleSummary>('/pharmacy/sales', payload)
  return data
}

export async function searchOtcSales(params: SaleSearchParams): Promise<SaleListResponse> {
  const { data } = await apiClient.get<SaleListResponse>('/pharmacy/sales', {
    params: {
      date_from: params.dateFrom || undefined,
      date_to: params.dateTo || undefined,
      payment_mode: params.paymentMode || undefined,
      status: params.status || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getOtcSale(saleId: string): Promise<SaleSummary> {
  const { data } = await apiClient.get<SaleSummary>(`/pharmacy/sales/${saleId}`)
  return data
}
