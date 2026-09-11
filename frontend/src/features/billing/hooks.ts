import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addLineItem,
  autoGenerateInvoice,
  createInvoice,
  deleteLineItem,
  getInvoice,
  getMyInvoices,
  issueInvoice,
  recordPayment,
  searchInvoices,
  updateInvoice,
  updateLineItem,
  voidInvoice,
} from '@/features/billing/api'
import type {
  AutoGenerateInvoiceRequest,
  InvoiceCreateRequest,
  InvoiceLineItemCreateRequest,
  InvoiceLineItemUpdateRequest,
  InvoiceSearchParams,
  InvoiceUpdateRequest,
  InvoiceVoidRequest,
  PaymentCreateRequest,
} from '@/features/billing/types'

export function useInvoiceSearch(params: InvoiceSearchParams) {
  return useQuery({
    queryKey: ['billing', 'invoices', 'search', params],
    queryFn: () => searchInvoices(params),
    placeholderData: keepPreviousData,
  })
}

// Patient portal only — billing.view_own, row-scoped server-side to the
// caller's own patient_id.
export function useMyInvoices() {
  return useQuery({
    queryKey: ['billing', 'invoices', 'me'],
    queryFn: () => getMyInvoices({}),
  })
}

export function useInvoice(invoiceId: string | undefined) {
  return useQuery({
    queryKey: ['billing', 'invoices', 'get', invoiceId],
    queryFn: () => getInvoice(invoiceId!),
    enabled: Boolean(invoiceId),
  })
}

function useInvalidateInvoices() {
  const queryClient = useQueryClient()
  return (invoiceId?: string) => {
    void queryClient.invalidateQueries({ queryKey: ['billing', 'invoices', 'search'] })
    if (invoiceId) void queryClient.invalidateQueries({ queryKey: ['billing', 'invoices', 'get', invoiceId] })
  }
}

export function useCreateInvoice() {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: InvoiceCreateRequest) => createInvoice(payload),
    onSuccess: () => invalidate(),
  })
}

export function useAutoGenerateInvoice() {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: AutoGenerateInvoiceRequest) => autoGenerateInvoice(payload),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateInvoice(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: InvoiceUpdateRequest) => updateInvoice(invoiceId, payload),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useAddLineItem(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: InvoiceLineItemCreateRequest) => addLineItem(invoiceId, payload),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useUpdateLineItem(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: InvoiceLineItemUpdateRequest }) =>
      updateLineItem(invoiceId, itemId, payload),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useDeleteLineItem(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (itemId: string) => deleteLineItem(invoiceId, itemId),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useIssueInvoice(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: () => issueInvoice(invoiceId),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useVoidInvoice(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: InvoiceVoidRequest) => voidInvoice(invoiceId, payload),
    onSuccess: () => invalidate(invoiceId),
  })
}

export function useRecordPayment(invoiceId: string) {
  const invalidate = useInvalidateInvoices()
  return useMutation({
    mutationFn: (payload: PaymentCreateRequest) => recordPayment(payload),
    onSuccess: () => invalidate(invoiceId),
  })
}
