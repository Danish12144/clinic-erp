import { ChevronLeft, Loader2, Search, UserRoundSearch } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useBranches } from '@/features/branches/hooks'
import { useAutoGenerateInvoice, useCreateInvoice } from '@/features/billing/hooks'
import type { InvoiceLineSource } from '@/features/billing/types'
import { searchEncounters } from '@/features/checkin/api'
import { usePatientSearch } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'

// A manually-created blank invoice needs its own source_type since it
// isn't tied to one auto-generated source the way auto-generate's
// CONSULTATION invoice is — this disambiguates it from any other
// invoice already raised against the same encounter (1-to-N, see
// backend/app/modules/billing/service.py's module docstring).
const MANUAL_SOURCE_TYPES: { value: InvoiceLineSource; label: string }[] = [
  { value: 'OTHER', label: 'General' },
  { value: 'PROCEDURE', label: 'Procedure' },
  { value: 'PHARMACY', label: 'Pharmacy' },
  { value: 'LAB', label: 'Lab' },
]

function encounterLabel(encounter: { checked_in_at: string; status: string }): string {
  return `${new Date(encounter.checked_in_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })} — ${encounter.status}`
}

export function NewInvoiceDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const [branchId, setBranchId] = useState('')
  const [encounterId, setEncounterId] = useState<string | undefined>(undefined)
  const [sourceType, setSourceType] = useState<InvoiceLineSource>('OTHER')

  const { data: searchResults, isFetching } = usePatientSearch(searchTerm)
  const { data: branches } = useBranches()
  const createInvoice = useCreateInvoice()
  const autoGenerate = useAutoGenerateInvoice()

  const encountersQuery = useQuery({
    queryKey: ['billing', 'new-invoice-encounters', selectedPatient?.id],
    queryFn: () => searchEncounters({ patientId: selectedPatient!.id, limit: 10 }),
    enabled: Boolean(selectedPatient),
  })

  // Auto-generate (POST /billing/invoices/auto-generate) 422s with "No
  // consultation has been started for this encounter yet" against an OPEN
  // encounter — the dropdown used to offer every encounter regardless of
  // status, so picking the (often most recent, still-OPEN) one was a real,
  // reachable "Could not create invoice" failure. Only offer encounters a
  // consultation actually exists for.
  const eligibleEncounters = useMemo(
    () => (encountersQuery.data?.items ?? []).filter((e) => e.status === 'IN_CONSULTATION' || e.status === 'COMPLETED'),
    [encountersQuery.data],
  )

  const branchSelectItems = useMemo(() => Object.fromEntries((branches ?? []).map((b) => [b.id, b.name])), [branches])
  // "Reason" per encounter isn't data this fetch has (chief_complaint lives
  // on the Consultation, not the Encounter, and joining it would mean one
  // extra request per row) — status is the closest available stand-in, so
  // the label is Date / Time / Status rather than a true reason.
  const encounterSelectItems = useMemo(
    () => Object.fromEntries(eligibleEncounters.map((e) => [e.id, encounterLabel(e)])),
    [eligibleEncounters],
  )
  const sourceTypeSelectItems = useMemo(() => Object.fromEntries(MANUAL_SOURCE_TYPES.map((o) => [o.value, o.label])), [])

  useEffect(() => {
    if (branches?.length === 1 && open) setBranchId(branches[0].id)
  }, [branches, open])

  useEffect(() => {
    if (!open) {
      setSearchTerm('')
      setSelectedPatient(null)
      setBranchId('')
      setEncounterId(undefined)
      setSourceType('OTHER')
    }
  }, [open])

  const isPending = createInvoice.isPending || autoGenerate.isPending

  async function handleCreate() {
    if (!selectedPatient || !branchId) return
    try {
      const invoice = encounterId
        ? await autoGenerate.mutateAsync({ encounter_id: encounterId })
        : await createInvoice.mutateAsync({ branch_id: branchId, patient_id: selectedPatient.id, source_type: sourceType })
      toast.success('Invoice created')
      onOpenChange(false)
      navigate(`/billing/${invoice.id}`)
    } catch (error) {
      toast.error('Could not create invoice', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New invoice</DialogTitle>
          <DialogDescription>Create a blank invoice, or auto-generate one from a consultation.</DialogDescription>
        </DialogHeader>

        {!selectedPatient ? (
          <div className="flex flex-col gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
              <Input
                autoFocus
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Phone, MRN, or name…"
                className="pl-8"
              />
              {isFetching && (
                <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-slate-400" />
              )}
            </div>
            <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200 dark:border-slate-800">
              {searchTerm.trim().length === 0 ? (
                <EmptyState icon={UserRoundSearch} title="Search for a patient" description="Type a phone number, MRN, or name to begin." />
              ) : !isFetching && searchResults?.items.length === 0 ? (
                <EmptyState icon={UserRoundSearch} title="No patients found" description="Try a different search term." />
              ) : (
                searchResults?.items.map((patient) => (
                  <button
                    key={patient.id}
                    type="button"
                    className="flex w-full flex-col gap-0.5 border-b border-slate-100 px-3 py-2 text-left last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                    onClick={() => setSelectedPatient(patient)}
                  >
                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
                    </span>
                    <span className="text-xs text-slate-500 dark:text-slate-400">
                      MRN {patient.mrn} {patient.phone ? `· ${patient.phone}` : ''}
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <button
              type="button"
              className="flex w-fit items-center gap-1 text-xs text-slate-500 hover:text-slate-900 dark:hover:text-slate-100"
              onClick={() => setSelectedPatient(null)}
            >
              <ChevronLeft className="size-3.5" />
              Change patient
            </button>

            <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                {[selectedPatient.first_name, selectedPatient.last_name].filter(Boolean).join(' ')}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">MRN {selectedPatient.mrn}</p>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Branch *</Label>
              {/* `items` is what makes the closed trigger show the branch
                  NAME instead of its raw UUID — see the same note on
                  IssueTokenDialog's Branch select. */}
              <Select value={branchId} onValueChange={(value) => setBranchId(value ?? '')} items={branchSelectItems}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select branch" />
                </SelectTrigger>
                <SelectContent>
                  {branches?.map((branch) => (
                    <SelectItem key={branch.id} value={branch.id}>
                      {branch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Auto-generate from consultation (optional)</Label>
              {encountersQuery.isLoading ? (
                <p className="text-xs text-slate-500">Loading encounters…</p>
              ) : eligibleEncounters.length > 0 ? (
                <Select value={encounterId ?? ''} onValueChange={(value) => setEncounterId(value || undefined)} items={encounterSelectItems}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Blank invoice — add line items manually" />
                  </SelectTrigger>
                  <SelectContent>
                    {eligibleEncounters.map((encounter) => (
                      <SelectItem key={encounter.id} value={encounter.id}>
                        {encounterLabel(encounter)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  No consultations found for this patient yet — will create a blank invoice.
                </p>
              )}
            </div>

            {!encounterId && (
              <div className="flex flex-col gap-1.5">
                <Label>Invoice type</Label>
                <Select value={sourceType} onValueChange={(value) => setSourceType((value ?? 'OTHER') as InvoiceLineSource)} items={sourceTypeSelectItems}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MANUAL_SOURCE_TYPES.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={!branchId || isPending} onClick={() => void handleCreate()}>
                {isPending ? 'Creating…' : 'Create invoice'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
