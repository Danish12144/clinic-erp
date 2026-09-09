// Mirrors backend/app/modules/billing/schemas.py — keep in sync with that file.

export const INVOICE_LINE_SOURCES = ['CONSULTATION', 'PROCEDURE', 'PHARMACY', 'LAB', 'OTHER'] as const
export type InvoiceLineSource = (typeof INVOICE_LINE_SOURCES)[number]

export const PAYMENT_METHODS = ['CASH', 'CARD', 'UPI', 'NET_BANKING', 'INSURANCE', 'OTHER'] as const
export type PaymentMethod = (typeof PAYMENT_METHODS)[number]

export interface InvoiceLineItemSummary {
  id: string
  invoice_id: string
  source_type: string
  source_id: string | null
  description: string
  quantity: string
  unit_price: string
  total: string
}

export interface PaymentSummary {
  id: string
  invoice_id: string
  amount: string
  method: string
  gateway_reference: string | null
  notes: string | null
  recorded_by: string
  recorded_at: string
}

export interface InvoiceSummary {
  id: string
  tenant_id: string
  branch_id: string
  encounter_id: string | null
  patient_id: string
  subtotal: string
  tax: string
  discount: string
  total: string
  status: string
  voided_at: string | null
  voided_reason: string | null
  total_paid: string
  balance_due: string
  created_at: string
  updated_at: string
  line_items: InvoiceLineItemSummary[]
  payments: PaymentSummary[]
}

export interface InvoiceListResponse {
  items: InvoiceSummary[]
  total: number
  limit: number
  offset: number
}

export interface PaymentListResponse {
  items: PaymentSummary[]
  total: number
  limit: number
  offset: number
}

export interface InvoiceSearchParams {
  branchId?: string
  patientId?: string
  encounterId?: string
  status?: string
  limit?: number
  offset?: number
}

export interface InvoiceLineItemCreateRequest {
  source_type: InvoiceLineSource
  source_id?: string | null
  description: string
  quantity?: string
  unit_price: string
}

export interface InvoiceCreateRequest {
  branch_id: string
  patient_id: string
  encounter_id?: string | null
  line_items?: InvoiceLineItemCreateRequest[]
  tax?: string
  discount?: string
}

export interface AutoGenerateInvoiceRequest {
  encounter_id: string
}

export interface InvoiceLineItemUpdateRequest {
  description?: string
  quantity?: string
  unit_price?: string
}

export interface InvoiceUpdateRequest {
  tax?: string
  discount?: string
}

export interface InvoiceVoidRequest {
  reason: string
}

export interface PaymentCreateRequest {
  invoice_id: string
  amount: string
  method: PaymentMethod
  gateway_reference?: string | null
  notes?: string | null
}
