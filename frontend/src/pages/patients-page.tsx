import { Loader2, Search, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { NewPatientDialog } from '@/components/patients/new-patient-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { usePatientSearch } from '@/features/patients/hooks'

function formatAge(dateOfBirth: string | null): string {
  if (!dateOfBirth) return '—'
  const years = Math.floor((Date.now() - new Date(dateOfBirth).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
  return `${years}y`
}

export function PatientsPage() {
  const { hasPermission } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const { data, isLoading, isFetching } = usePatientSearch(searchTerm)

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Patients</h1>
          <p className="text-sm text-muted-foreground">Search by phone, MRN, or name.</p>
        </div>
        {hasPermission('patients.register') && (
          <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
            <UserPlus className="size-4" />
            New patient
          </Button>
        )}
      </div>

      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="Phone, MRN, or name…"
          className="pl-8"
        />
        {isFetching && !isLoading && (
          <Loader2 className="absolute top-1/2 right-2.5 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
      </div>

      <div className="rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>MRN</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Age / Gender</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Email</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-32" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && data?.items.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                  No patients found.
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              data?.items.map((patient) => (
                <TableRow key={patient.id}>
                  <TableCell className="font-mono text-xs">{patient.mrn}</TableCell>
                  <TableCell className="font-medium">
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
                  <TableCell>{patient.phone ?? '—'}</TableCell>
                  <TableCell>{patient.email ?? '—'}</TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {data && (
        <p className="text-xs text-muted-foreground">
          {data.total} patient{data.total === 1 ? '' : 's'} found
        </p>
      )}

      <NewPatientDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}
