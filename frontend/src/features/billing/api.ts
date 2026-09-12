import { apiClient } from '@/lib/api-client'
import type {
  AutoGenerateInvoiceRequest,
  InvoiceCreateRequest,
  InvoiceLineItemCreateRequest,
  InvoiceLineItemUpdateRequest,
  InvoiceListResponse,
  InvoiceSearchParams,
  InvoiceSummary,
  InvoiceUpdateRequest,
  InvoiceVoidRequest,
  PaymentCreateRequest,
  PaymentSummary,
} from '@/features/billing/types'

export async function searchInvoices(params: InvoiceSearchParams): Promise<InvoiceListResponse> {
  const { data } = await apiClient.get<InvoiceListResponse>('/billing/invoices', {
    params: {
      branch_id: params.branchId || undefined,
      patient_id: params.patientId || undefined,
      encounter_id: params.encounterId || undefined,
      status: params.status || undefined,
      limit: params.limit ?? 20,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getMyInvoices(params: { limit?: number; offset?: number }): Promise<InvoiceListResponse> {
  const { data } = await apiClient.get<InvoiceListResponse>('/billing/invoices/me', {
    params: { limit: params.limit ?? 20, offset: params.offset ?? 0 },
  })
  return data
}

export async function getInvoice(invoiceId: string): Promise<InvoiceSummary> {
  const { data } = await apiClient.get<InvoiceSummary>(`/billing/invoices/${invoiceId}`)
  return data
}

export async function createInvoice(payload: InvoiceCreateRequest): Promise<InvoiceSummary> {
  const { data } = await apiClient.post<InvoiceSummary>('/billing/invoices', payload)
  return data
}

export async function autoGenerateInvoice(payload: AutoGenerateInvoiceRequest): Promise<InvoiceSummary> {
  const { data } = await apiClient.post<InvoiceSummary>('/billing/invoices/auto-generate', payload)
  return data
}

export async function updateInvoice(invoiceId: string, payload: InvoiceUpdateRequest): Promise<InvoiceSummary> {
  const { data } = await apiClient.patch<InvoiceSummary>(`/billing/invoices/${invoiceId}`, payload)
  return data
}

export async function addLineItem(invoiceId: string, payload: InvoiceLineItemCreateRequest): Promise<InvoiceSummary> {
  const { data } = await apiClient.post<InvoiceSummary>(`/billing/invoices/${invoiceId}/line-items`, payload)
  return data
}

export async function updateLineItem(
  invoiceId: string,
  itemId: string,
  payload: InvoiceLineItemUpdateRequest,
): Promise<InvoiceSummary> {
  const { data } = await apiClient.patch<InvoiceSummary>(`/billing/invoices/${invoiceId}/line-items/${itemId}`, payload)
  return data
}

export async function deleteLineItem(invoiceId: string, itemId: string): Promise<InvoiceSummary> {
  const { data } = await apiClient.delete<InvoiceSummary>(`/billing/invoices/${invoiceId}/line-items/${itemId}`)
  return data
}

export async function issueInvoice(invoiceId: string): Promise<InvoiceSummary> {
  const { data } = await apiClient.post<InvoiceSummary>(`/billing/invoices/${invoiceId}/issue`)
  return data
}

export async function voidInvoice(invoiceId: string, payload: InvoiceVoidRequest): Promise<InvoiceSummary> {
  const { data } = await apiClient.post<InvoiceSummary>(`/billing/invoices/${invoiceId}/void`, payload)
  return data
}

export async function recordPayment(payload: PaymentCreateRequest): Promise<PaymentSummary> {
  const { data } = await apiClient.post<PaymentSummary>('/billing/payments', payload)
  return data
}

// Phase 1 (Master Handoff item 6) — same filters as searchInvoices, a CSV
// file instead of JSON. `status` (not `status_filter`) is deliberately not
// renamed on the frontend side even though the backend's alias mirrors
// searchInvoices' own naming, to stay consistent with InvoiceSearchParams.
export async function exportInvoicesCsv(params: Pick<InvoiceSearchParams, 'branchId' | 'patientId' | 'encounterId' | 'status'>): Promise<Blob> {
  const { data } = await apiClient.get<Blob>('/billing/invoices/export', {
    params: {
      branch_id: params.branchId || undefined,
      patient_id: params.patientId || undefined,
      encounter_id: params.encounterId || undefined,
      status: params.status || undefined,
    },
    responseType: 'blob',
  })
  return data
}
