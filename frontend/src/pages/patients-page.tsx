import { Loader2, Pencil, Search, UserPlus, UserRoundSearch } from 'lucide-react'
import { useState } from 'react'
import { EditPatientDialog } from '@/components/patients/edit-patient-dialog'
import { NewPatientDialog } from '@/components/patients/new-patient-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { usePatientSearch } from '@/features/patients/hooks'
import type { PatientSummary } from '@/features/patients/types'

function formatAge(dateOfBirth: string | null): string {
  if (!dateOfBirth) return '—'
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

export function PatientsPage() {
  const { hasPermission } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingPatient, setEditingPatient] = useState<PatientSummary | null>(null)
  const { data, isLoading, isFetching } = usePatientSearch(searchTerm)
  const canEdit = hasPermission('patients.register')

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Patients</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Search by phone, MRN, or name.</p>
        </div>
        {hasPermission('patients.register') && (
          <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
            <UserPlus className="size-4" />
            New patient
          </Button>
        )}
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" />
        <Input
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="Phone, MRN, or name…"
          className="pl-8"
        />
        {isFetching && !isLoading && (
          <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-slate-400" />
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>MRN</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Age / Gender</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Email</TableHead>
              {canEdit && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: canEdit ? 6 : 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-32" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && data?.items.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={canEdit ? 6 : 5}>
                  <EmptyState
                    icon={UserRoundSearch}
                    title="No patients found"
                    description="Try a different search, or register a new patient to get started."
                  />
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              data?.items.map((patient) => (
                <TableRow key={patient.id}>
                  <TableCell className="font-mono text-xs text-slate-500">{patient.mrn}</TableCell>
                  <TableCell className="font-medium text-slate-900 dark:text-slate-100">
                    {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
                  </TableCell>
                  <TableCell>
                    {formatAge(patient.date_of_birth)}
                    {patient.gender && (
                      <Badge variant="secondary" className="ml-1.5">
                        {patient.gender}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{patient.phone ?? '—'}</TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{patient.email ?? '—'}</TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setEditingPatient(patient)}>
                        <Pencil className="size-4" />
                        Edit
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {data && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {data.total} patient{data.total === 1 ? '' : 's'} found
        </p>
      )}

      <NewPatientDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      <EditPatientDialog
        patient={editingPatient}
        open={editingPatient !== null}
        onOpenChange={(next) => {
          if (!next) setEditingPatient(null)
        }}
      />
    </div>
  )
}
