import { Phone, Plus, UserRoundPlus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { LeadDetailDialog } from '@/components/leads/lead-detail-dialog'
import { NewLeadDialog } from '@/components/leads/new-lead-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/features/auth/auth-context'
import { useLeadSearch } from '@/features/leads/hooks'
import { LEAD_SOURCE_LABELS, LEAD_STATUSES, LEAD_STATUS_LABELS, type LeadSummary } from '@/features/leads/types'

function LeadCard({ lead, onOpen }: { lead: LeadSummary; onOpen: (lead: LeadSummary) => void }) {
  return (
    <Card size="sm" className="cursor-pointer transition-shadow hover:shadow-md" onClick={() => onOpen(lead)}>
      <CardContent className="flex flex-col gap-1.5">
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
          {lead.first_name} {lead.last_name}
        </p>
        {lead.phone && (
          <p className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
            <Phone className="size-3" />
            {lead.phone}
          </p>
        )}
        {lead.source && (
          <Badge variant="secondary" className="w-fit text-[0.65rem]">
            {LEAD_SOURCE_LABELS[lead.source]}
          </Badge>
        )}
        {lead.notes && <p className="line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{lead.notes}</p>}
        <p className="text-[0.65rem] text-slate-400 dark:text-slate-600">{new Date(lead.created_at).toLocaleDateString()}</p>
      </CardContent>
    </Card>
  )
}

export function LeadsPage() {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('leads.manage')
  const [selectedLead, setSelectedLead] = useState<LeadSummary | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [newLeadOpen, setNewLeadOpen] = useState(false)

  const { data, isLoading } = useLeadSearch({ limit: 100 })
  const leads = data?.items ?? []

  const byStatus = useMemo(() => {
    const grouped = Object.fromEntries(LEAD_STATUSES.map((status) => [status, [] as LeadSummary[]])) as Record<string, LeadSummary[]>
    for (const lead of leads) grouped[lead.status]?.push(lead)
    return grouped
  }, [leads])

  function openLead(lead: LeadSummary) {
    setSelectedLead(lead)
    setDetailOpen(true)
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Leads</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Inbound inquiries, from first contact to conversion.</p>
        </div>
        {canManage && (
          <Button className="gap-1.5" onClick={() => setNewLeadOpen(true)}>
            <Plus className="size-4" />
            New lead
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {LEAD_STATUSES.map((status) => (
            <div key={status} className="flex flex-col gap-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ))}
        </div>
      ) : leads.length === 0 ? (
        <EmptyState
          icon={UserRoundPlus}
          title="No leads yet"
          description={canManage ? 'Add a lead to start tracking inbound inquiries.' : 'No leads have been added yet.'}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {LEAD_STATUSES.map((status) => (
            <div key={status} className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="text-xs font-medium text-slate-400 dark:text-slate-500">{byStatus[status]?.length ?? 0}</span>
              </div>
              <div className="flex flex-col gap-2">
                {byStatus[status]?.length === 0 && (
                  <p className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400 dark:border-slate-800 dark:text-slate-600">
                    {LEAD_STATUS_LABELS[status]} — none
                  </p>
                )}
                {byStatus[status]?.map((lead) => (
                  <LeadCard key={lead.id} lead={lead} onOpen={openLead} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <LeadDetailDialog lead={selectedLead} open={detailOpen} onOpenChange={setDetailOpen} />
      <NewLeadDialog open={newLeadOpen} onOpenChange={setNewLeadOpen} />
    </div>
  )
}
