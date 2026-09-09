// Mirrors backend/app/modules/pharmacy/schemas.py — keep in sync with that file.

export interface MedicineSummary {
  id: string
  name: string
  generic_name: string | null
  category: string | null
  dosage_form: string | null
  strength: string | null
  manufacturer: string | null
  unit_price: string
  sku: string | null
  reorder_threshold: number
  is_active: boolean
  total_stock: number
  is_below_reorder_threshold: boolean
}

export interface MedicineListResponse {
  items: MedicineSummary[]
  total: number
  limit: number
  offset: number
}

export interface MedicineSearchParams {
  q?: string
  category?: string
  isActive?: boolean
  lowStockOnly?: boolean
  limit?: number
  offset?: number
}

export interface MedicineCreateRequest {
  name: string
  generic_name?: string | null
  category?: string | null
  dosage_form?: string | null
  strength?: string | null
  manufacturer?: string | null
  unit_price?: string
  sku?: string | null
  reorder_threshold?: number
}

export interface MedicineUpdateRequest {
  name?: string
  generic_name?: string | null
  category?: string | null
  dosage_form?: string | null
  strength?: string | null
  manufacturer?: string | null
  unit_price?: string
  sku?: string | null
  reorder_threshold?: number
  is_active?: boolean
}

export interface MedicineBatchSummary {
  id: string
  medicine_id: string
  batch_number: string
  expiry_date: string
  quantity_on_hand: number
  cost_price: string | null
}

export interface MedicineBatchListResponse {
  items: MedicineBatchSummary[]
  total: number
  limit: number
  offset: number
}

export interface ReceiveStockRequest {
  batch_number: string
  expiry_date: string
  quantity: number
  cost_price?: string | null
}

export interface DispenseRequest {
  prescription_item_id: string
  quantity: number
}

export interface DispenseAllocation {
  batch_id: string
  batch_number: string
  quantity: number
}

export interface DispenseResult {
  prescription_item_id: string
  medicine_id: string
  quantity_dispensed: number
  prescription_item_dispensed_quantity: number
  allocations: DispenseAllocation[]
}

export const PHARMACY_PAYMENT_METHODS = ['CASH', 'CARD', 'UPI', 'NET_BANKING', 'INSURANCE', 'OTHER'] as const
export type PharmacyPaymentMethod = (typeof PHARMACY_PAYMENT_METHODS)[number]

export interface OTCSaleCartItem {
  medicine_id: string
  quantity: number
}

export interface OTCSaleCreateRequest {
  customer_name?: string | null
  customer_phone?: string | null
  items: OTCSaleCartItem[]
  discount_amount?: string
  payment_mode: PharmacyPaymentMethod
}

export interface SaleItemSummary {
  id: string
  medicine_id: string
  batch_id: string
  quantity: number
  unit_price: string
  total_price: string
}

export interface SaleSummary {
  id: string
  customer_name: string | null
  customer_phone: string | null
  total_amount: string
  discount_amount: string
  net_amount: string
  payment_mode: string
  status: string
  created_at: string
  items: SaleItemSummary[]
}

export interface SaleListResponse {
  items: SaleSummary[]
  total: number
  limit: number
  offset: number
  total_net_amount: string
}

export interface SaleSearchParams {
  dateFrom?: string
  dateTo?: string
  paymentMode?: string
  status?: string
  limit?: number
  offset?: number
}
