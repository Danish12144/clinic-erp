// Mirrors backend/app/modules/inventory/schemas.py + models.py — keep in sync with those files.

export const INVENTORY_ITEM_CATEGORIES = ['CONSUMABLE', 'EQUIPMENT', 'LAB_SUPPLY', 'OFFICE'] as const
export type InventoryItemCategory = (typeof INVENTORY_ITEM_CATEGORIES)[number]

export const INVENTORY_UNITS = ['PIECES', 'PACKS', 'BOXES'] as const
export type InventoryUnit = (typeof INVENTORY_UNITS)[number]

export const INVENTORY_CHANGE_TYPES = ['PURCHASE', 'USAGE', 'ADJUSTMENT', 'RETURN'] as const
export type InventoryChangeType = (typeof INVENTORY_CHANGE_TYPES)[number]

export interface InventoryItemSummary {
  id: string
  tenant_id: string
  name: string
  category: InventoryItemCategory
  unit: InventoryUnit
  current_stock: string
  min_reorder_level: string
  cost_per_unit: string
  is_active: boolean
  is_below_reorder_level: boolean
  created_at: string
  updated_at: string
}

export interface InventoryItemListResponse {
  items: InventoryItemSummary[]
  total: number
  limit: number
  offset: number
}

export interface InventoryItemSearchParams {
  category?: InventoryItemCategory
  isActive?: boolean
  lowStockOnly?: boolean
  limit?: number
  offset?: number
}

export interface InventoryItemCreateRequest {
  name: string
  category: InventoryItemCategory
  unit: InventoryUnit
  min_reorder_level?: string
  cost_per_unit?: string
}

export interface InventoryItemUpdateRequest {
  name?: string
  category?: InventoryItemCategory
  unit?: InventoryUnit
  min_reorder_level?: string
  cost_per_unit?: string
  is_active?: boolean
}

export interface InventoryTransactionCreateRequest {
  change_type: InventoryChangeType
  quantity: string
  reference_id?: string
  notes?: string
}

export interface InventoryTransactionSummary {
  id: string
  tenant_id: string
  item_id: string
  change_type: InventoryChangeType
  quantity: string
  reference_id: string | null
  performed_by: string
  notes: string | null
  created_at: string
  resulting_stock: string
}
