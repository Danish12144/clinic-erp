import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { convertLead, createLead, getLead, logLeadInteraction, searchLeads, updateLead } from '@/features/leads/api'
import { useAuth } from '@/features/auth/auth-context'
import type {
  LeadConvertRequest,
  LeadCreateRequest,
  LeadInteractionCreateRequest,
  LeadSearchParams,
  LeadUpdateRequest,
} from '@/features/leads/types'

const READ_PERMS = ['leads.manage', 'leads.view']

export function useLeadSearch(params: LeadSearchParams) {
  const { hasPermission } = useAuth()
  return useQuery({
    queryKey: ['leads', 'search', params],
    queryFn: () => searchLeads(params),
    enabled: READ_PERMS.some(hasPermission),
  })
}

export function useLead(leadId: string | null) {
  return useQuery({
    queryKey: ['leads', 'get', leadId],
    queryFn: () => getLead(leadId!),
    enabled: Boolean(leadId),
  })
}

function useInvalidateLeads() {
  const queryClient = useQueryClient()
  return () => void queryClient.invalidateQueries({ queryKey: ['leads'] })
}

export function useCreateLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: (payload: LeadCreateRequest) => createLead(payload),
    onSuccess: invalidate,
  })
}

export function useUpdateLead() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: ({ leadId, payload }: { leadId: string; payload: LeadUpdateRequest }) => updateLead(leadId, payload),
    onSuccess: invalidate,
  })
}

export function useLogLeadInteraction() {
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: ({ leadId, payload }: { leadId: string; payload: LeadInteractionCreateRequest }) => logLeadInteraction(leadId, payload),
    onSuccess: invalidate,
  })
}

export function useConvertLead() {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateLeads()
  return useMutation({
    mutationFn: ({ leadId, payload }: { leadId: string; payload: LeadConvertRequest }) => convertLead(leadId, payload),
    onSuccess: () => {
      invalidate()
      // Conversion creates a new Patient row — the Patients search page's
      // cached results would otherwise miss it until an unrelated refetch.
      void queryClient.invalidateQueries({ queryKey: ['patients'] })
    },
  })
}
