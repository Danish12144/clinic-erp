import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { StatusBadge } from '@/components/shared/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/features/auth/auth-context'
import { useConvertLead, useLogLeadInteraction, useUpdateLead } from '@/features/leads/hooks'
import {
  LEAD_CONVERTIBLE_STATUSES,
  LEAD_INTERACTION_TYPES,
  LEAD_MANUAL_STATUSES,
  LEAD_SOURCE_LABELS,
  LEAD_STATUS_LABELS,
  type LeadInteractionType,
  type LeadSummary,
} from '@/features/leads/types'
import { getPatient } from '@/features/patients/api'
import { getErrorMessage } from '@/lib/errors'

function ConvertedPatientNote({ patientId }: { patientId: string }) {
  const { data: patient } = useQuery({ queryKey: ['patients', 'get', patientId], queryFn: () => getPatient(patientId) })
  return (
    <p className="text-sm text-emerald-700 dark:text-emerald-400">
      Converted to patient {patient ? `${patient.first_name} ${patient.last_name ?? ''} (${patient.mrn})`.trim() : patientId.slice(0, 8)}.
    </p>
  )
}

export function LeadDetailDialog({ lead, open, onOpenChange }: { lead: LeadSummary | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { hasPermission } = useAuth()
  const canManage = hasPermission('leads.manage')
  const updateLead = useUpdateLead()
  const logInteraction = useLogLeadInteraction()
  const convertLead = useConvertLead()

  const [interactionType, setInteractionType] = useState<LeadInteractionType>('CALL')
  const [interactionOutcome, setInteractionOutcome] = useState('')
  const [interactionNotes, setInteractionNotes] = useState('')
  const [convertOpen, setConvertOpen] = useState(false)
  const [convertGender, setConvertGender] = useState<'' | 'Male' | 'Female' | 'Other'>('')
  const [convertDob, setConvertDob] = useState('')
  const [convertAddress, setConvertAddress] = useState('')

  if (!lead) return null

  const canConvert = canManage && (LEAD_CONVERTIBLE_STATUSES as readonly string[]).includes(lead.status)

  async function handleStatusChange(status: string) {
    if (!lead || !status || status === lead.status) return
    try {
      await updateLead.mutateAsync({ leadId: lead.id, payload: { status: status as (typeof LEAD_MANUAL_STATUSES)[number] } })
      toast.success('Lead status updated')
    } catch (error) {
      toast.error('Could not update status', { description: getErrorMessage(error) })
    }
  }

  async function handleLogInteraction() {
    if (!lead) return
    try {
      await logInteraction.mutateAsync({
        leadId: lead.id,
        payload: { interaction_type: interactionType, outcome: interactionOutcome || undefined, notes: interactionNotes || undefined },
      })
      toast.success('Interaction logged')
      setInteractionOutcome('')
      setInteractionNotes('')
    } catch (error) {
      toast.error('Could not log interaction', { description: getErrorMessage(error) })
    }
  }

  async function handleConvert() {
    if (!lead) return
    try {
      const result = await convertLead.mutateAsync({
        leadId: lead.id,
        payload: {
          gender: convertGender || undefined,
          date_of_birth: convertDob || undefined,
          address: convertAddress || undefined,
        },
      })
      toast.success('Lead converted to patient', { description: `Patient record created (${result.patient_id.slice(0, 8)}…).` })
      setConvertOpen(false)
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not convert lead', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {lead.first_name} {lead.last_name}
            <StatusBadge status={lead.status} />
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Phone</p>
              <p className="text-slate-900 dark:text-slate-100">{lead.phone || '—'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Email</p>
              <p className="text-slate-900 dark:text-slate-100">{lead.email || '—'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Source</p>
              {lead.source ? <Badge variant="secondary">{LEAD_SOURCE_LABELS[lead.source]}</Badge> : <p className="text-slate-500">—</p>}
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Added</p>
              <p className="text-slate-900 dark:text-slate-100">{new Date(lead.created_at).toLocaleDateString()}</p>
            </div>
          </div>

          {lead.notes && (
            <div>
              <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Notes</p>
              <p className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">{lead.notes}</p>
            </div>
          )}

          {lead.converted_patient_id && <ConvertedPatientNote patientId={lead.converted_patient_id} />}

          {canManage && lead.status !== 'CONVERTED' && (
            <div className="flex flex-col gap-1.5 border-t border-slate-200 pt-3 dark:border-slate-800">
              <Label>Move to stage</Label>
              <Select value={lead.status} onValueChange={(value) => value && void handleStatusChange(value)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LEAD_MANUAL_STATUSES.map((status) => (
                    <SelectItem key={status} value={status}>
                      {LEAD_STATUS_LABELS[status]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {canManage && (
            <div className="flex flex-col gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
              <Label>Log an interaction</Label>
              <div className="grid grid-cols-2 gap-2">
                <Select value={interactionType} onValueChange={(value) => value && setInteractionType(value as LeadInteractionType)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LEAD_INTERACTION_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {type}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input placeholder="Outcome (optional)" value={interactionOutcome} onChange={(e) => setInteractionOutcome(e.target.value)} />
              </div>
              <Textarea
                rows={2}
                placeholder="Notes (optional)"
                value={interactionNotes}
                onChange={(e) => setInteractionNotes(e.target.value)}
              />
              <Button type="button" variant="outline" size="sm" className="self-start" disabled={logInteraction.isPending} onClick={() => void handleLogInteraction()}>
                {logInteraction.isPending ? 'Logging…' : 'Log interaction'}
              </Button>
            </div>
          )}

          {canConvert && (
            <div className="flex flex-col gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
              {!convertOpen ? (
                <Button type="button" className="self-start" onClick={() => setConvertOpen(true)}>
                  Convert to patient
                </Button>
              ) : (
                <>
                  <Label>Convert to patient</Label>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Creates a patient record from this lead's name/phone/email. These fields are optional extras.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <Select value={convertGender} onValueChange={(value) => setConvertGender((value ?? '') as typeof convertGender)}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Gender" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Male">Male</SelectItem>
                        <SelectItem value="Female">Female</SelectItem>
                        <SelectItem value="Other">Other</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input type="date" value={convertDob} onChange={(e) => setConvertDob(e.target.value)} />
                  </div>
                  <Textarea rows={2} placeholder="Address (optional)" value={convertAddress} onChange={(e) => setConvertAddress(e.target.value)} />
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => setConvertOpen(false)}>
                      Cancel
                    </Button>
                    <Button type="button" size="sm" disabled={convertLead.isPending} onClick={() => void handleConvert()}>
                      {convertLead.isPending ? 'Converting…' : 'Confirm conversion'}
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
