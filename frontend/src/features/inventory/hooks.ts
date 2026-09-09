import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createInventoryItem,
  listLowStockAlerts,
  recordInventoryTransaction,
  searchInventoryItems,
  updateInventoryItem,
} from '@/features/inventory/api'
import { useAuth } from '@/features/auth/auth-context'
import type {
  InventoryItemCreateRequest,
  InventoryItemSearchParams,
  InventoryItemUpdateRequest,
  InventoryTransactionCreateRequest,
} from '@/features/inventory/types'

const READ_PERMS = ['inventory.manage', 'inventory.record_usage', 'inventory.view']

export function useInventoryItems(params: InventoryItemSearchParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['inventory', 'items', 'search', params],
    queryFn: () => searchInventoryItems(params),
    enabled: READ_PERMS.some(hasPermission),
    placeholderData: keepPreviousData,
  })
}

export function useLowStockAlerts() {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['inventory', 'items', 'low-stock'],
    queryFn: listLowStockAlerts,
    enabled: READ_PERMS.some(hasPermission),
  })
}

function useInvalidateInventoryItems() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['inventory', 'items'] })
}

export function useCreateInventoryItem() {
  const invalidate = useInvalidateInventoryItems()
  return useMutation({
    mutationFn: (payload: InventoryItemCreateRequest) => createInventoryItem(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateInventoryItem() {
  const invalidate = useInvalidateInventoryItems()
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: InventoryItemUpdateRequest }) => updateInventoryItem(itemId, payload),
    onSuccess: invalidate,
  })
}

export function useRecordInventoryTransaction() {
  const invalidate = useInvalidateInventoryItems()
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: InventoryTransactionCreateRequest }) =>
      recordInventoryTransaction(itemId, payload),
    onSuccess: invalidate,
  })
}
