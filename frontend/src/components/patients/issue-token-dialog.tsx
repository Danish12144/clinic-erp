import { ChevronLeft, Loader2, Search, UserRoundSearch } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useBranches } from '@/features/branches/hooks'
import { useRegisterWalkIn } from '@/features/checkin/hooks'
import { useDoctorDirectory } from '@/features/doctors/hooks'
import { usePatientSearch } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'

// Distinct from NewPatientDialog: this checks in a patient who is ALREADY
// registered (no demographics form) — search, pick, issue. The write it
// performs is the same POST /encounters/walk-in either way; only the
// front-desk workflow differs.
export function IssueTokenDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null)
  const [branchId, setBranchId] = useState('')
  const [doctorId, setDoctorId] = useState<string | undefined>(undefined)

  const { data: searchResults, isFetching } = usePatientSearch(searchTerm)
  const { data: branches } = useBranches()
  const { data: directory } = useDoctorDirectory()
  const registerWalkIn = useRegisterWalkIn()

  const branchSelectItems = useMemo(() => Object.fromEntries((branches ?? []).map((b) => [b.id, b.name])), [branches])
  const doctorSelectItems = useMemo(
    () => Object.fromEntries((directory?.items ?? []).map((d) => [d.user_id, [d.first_name, d.last_name].filter(Boolean).join(' ')])),
    [directory],
  )

  useEffect(() => {
    if (branches?.length === 1 && open) setBranchId(branches[0].id)
  }, [branches, open])

  useEffect(() => {
    if (!open) {
      setSearchTerm('')
      setSelectedPatient(null)
      setBranchId('')
      setDoctorId(undefined)
    }
  }, [open])

  async function handleIssue() {
    if (!selectedPatient || !branchId) return
    try {
      const result = await registerWalkIn.mutateAsync({ patient_id: selectedPatient.id, branch_id: branchId, doctor_id: doctorId })
      const name = [selectedPatient.first_name, selectedPatient.last_name].filter(Boolean).join(' ')
      toast.success(`Token #${result.queue_token.token_number} issued for ${name}`)
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not issue token', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Issue token</DialogTitle>
          <DialogDescription>Check in an already-registered patient and issue a queue token.</DialogDescription>
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
                  NAME instead of its raw UUID — base-ui's Select.Value only
                  resolves a label from this map (or an `itemToStringLabel`),
                  never from the SelectItem children rendered in the popup;
                  without it, the trigger falls back to printing the raw
                  `value` string once something is selected. */}
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

            {directory && directory.items.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label>Doctor (optional)</Label>
                <Select value={doctorId ?? ''} onValueChange={(value) => setDoctorId(value || undefined)} items={doctorSelectItems}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Assign later" />
                  </SelectTrigger>
                  <SelectContent>
                    {directory.items.map((doctor) => (
                      <SelectItem key={doctor.user_id} value={doctor.user_id}>
                        {[doctor.first_name, doctor.last_name].filter(Boolean).join(' ')}
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
              <Button type="button" disabled={!branchId || registerWalkIn.isPending} onClick={() => void handleIssue()}>
                {registerWalkIn.isPending ? 'Issuing…' : 'Issue token'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
