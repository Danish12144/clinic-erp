import { apiClient } from '@/lib/api-client'
import type {
  InventoryItemCreateRequest,
  InventoryItemListResponse,
  InventoryItemSearchParams,
  InventoryItemSummary,
  InventoryItemUpdateRequest,
  InventoryTransactionCreateRequest,
  InventoryTransactionSummary,
} from '@/features/inventory/types'

export async function searchInventoryItems(params: InventoryItemSearchParams): Promise<InventoryItemListResponse> {
  const { data } = await apiClient.get<InventoryItemListResponse>('/inventory/items', {
    params: {
      category: params.category || undefined,
      is_active: params.isActive,
      low_stock_only: params.lowStockOnly || undefined,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getInventoryItem(itemId: string): Promise<InventoryItemSummary> {
  const { data } = await apiClient.get<InventoryItemSummary>(`/inventory/items/${itemId}`)
  return data
}

export async function createInventoryItem(payload: InventoryItemCreateRequest): Promise<InventoryItemSummary> {
  const { data } = await apiClient.post<InventoryItemSummary>('/inventory/items', payload)
  return data
}

export async function updateInventoryItem(itemId: string, payload: InventoryItemUpdateRequest): Promise<InventoryItemSummary> {
  const { data } = await apiClient.patch<InventoryItemSummary>(`/inventory/items/${itemId}`, payload)
  return data
}

export async function recordInventoryTransaction(
  itemId: string,
  payload: InventoryTransactionCreateRequest,
): Promise<InventoryTransactionSummary> {
  const { data } = await apiClient.post<InventoryTransactionSummary>(`/inventory/items/${itemId}/transactions`, payload)
  return data
}

export async function listLowStockAlerts(): Promise<InventoryItemSummary[]> {
  const { data } = await apiClient.get<InventoryItemSummary[]>('/inventory/alerts/low-stock')
  return data
}
