import { apiClient } from '@/lib/api-client'
import type {
  LeadConvertRequest,
  LeadConvertResponse,
  LeadCreateRequest,
  LeadInteractionCreateRequest,
  LeadInteractionSummary,
  LeadListResponse,
  LeadSearchParams,
  LeadSummary,
  LeadUpdateRequest,
} from '@/features/leads/types'

export async function searchLeads(params: LeadSearchParams): Promise<LeadListResponse> {
  const { data } = await apiClient.get<LeadListResponse>('/leads', {
    params: {
      status: params.status || undefined,
      source: params.source || undefined,
      limit: params.limit ?? 100,
      offset: params.offset ?? 0,
    },
  })
  return data
}

export async function getLead(leadId: string): Promise<LeadSummary> {
  const { data } = await apiClient.get<LeadSummary>(`/leads/${leadId}`)
  return data
}

export async function createLead(payload: LeadCreateRequest): Promise<LeadSummary> {
  const { data } = await apiClient.post<LeadSummary>('/leads', payload)
  return data
}

export async function updateLead(leadId: string, payload: LeadUpdateRequest): Promise<LeadSummary> {
  const { data } = await apiClient.patch<LeadSummary>(`/leads/${leadId}`, payload)
  return data
}

export async function logLeadInteraction(leadId: string, payload: LeadInteractionCreateRequest): Promise<LeadInteractionSummary> {
  const { data } = await apiClient.post<LeadInteractionSummary>(`/leads/${leadId}/interactions`, payload)
  return data
}

export async function convertLead(leadId: string, payload: LeadConvertRequest): Promise<LeadConvertResponse> {
  const { data } = await apiClient.post<LeadConvertResponse>(`/leads/${leadId}/convert`, payload)
  return data
}
