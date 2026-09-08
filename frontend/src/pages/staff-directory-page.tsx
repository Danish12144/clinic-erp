import { UserPlus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { RoleBadge } from '@/components/staff/role-badge'
import { InviteStaffDialog } from '@/components/staff/invite-staff-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useDoctors } from '@/features/doctors/hooks'
import { useStaff } from '@/features/staff/hooks'
import { useDebouncedValue } from '@/lib/use-debounced-value'

interface DirectoryRow {
  userId: string
  roleCode: string
  name: string
  email: string | null
  phone: string | null
  status: string
  detail: string | null
}

export function StaffDirectoryPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const debouncedTerm = useDebouncedValue(searchTerm, 350)

  const staffQuery = useStaff({ q: debouncedTerm, includeInactive: true })
  const doctorsQuery = useDoctors({ q: debouncedTerm, includeInactive: true })
  const isLoading = staffQuery.isLoading || doctorsQuery.isLoading

  const rows = useMemo<DirectoryRow[]>(() => {
    const staffRows: DirectoryRow[] = (staffQuery.data?.items ?? []).map((s) => ({
      userId: s.user_id,
      roleCode: s.role_code,
      name: [s.first_name, s.last_name].filter(Boolean).join(' ') || '—',
      email: s.email,
      phone: s.phone,
      status: s.status,
      detail: s.designation,
    }))
    const doctorRows: DirectoryRow[] = (doctorsQuery.data?.items ?? []).map((d) => ({
      userId: d.user_id,
      roleCode: 'DOCTOR',
      name: [d.first_name, d.last_name].filter(Boolean).join(' ') || '—',
      email: d.email,
      phone: d.phone,
      status: d.status,
      detail: d.specialization,
    }))
    return [...doctorRows, ...staffRows].sort((a, b) => a.name.localeCompare(b.name))
  }, [staffQuery.data, doctorsQuery.data])

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Staff Directory</h1>
          <p className="text-sm text-muted-foreground">All clinic staff, including doctors.</p>
        </div>
        <Button onClick={() => setDialogOpen(true)} className="gap-1.5">
          <UserPlus className="size-4" />
          Invite staff
        </Button>
      </div>

      <Input
        value={searchTerm}
        onChange={(event) => setSearchTerm(event.target.value)}
        placeholder="Search by name…"
        className="max-w-sm"
      />

      <div className="rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Designation / Specialization</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 6 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-28" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}

            {!isLoading && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                  No staff found.
                </TableCell>
              </TableRow>
            )}

            {!isLoading &&
              rows.map((row) => (
                <TableRow key={row.userId}>
                  <TableCell className="font-medium">{row.name}</TableCell>
                  <TableCell>
                    <RoleBadge roleCode={row.roleCode} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{row.detail ?? '—'}</TableCell>
                  <TableCell>{row.email ?? '—'}</TableCell>
                  <TableCell>{row.phone ?? '—'}</TableCell>
                  <TableCell>
                    <Badge variant={row.status === 'ACTIVE' ? 'secondary' : 'outline'}>{row.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      <InviteStaffDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  )
}
