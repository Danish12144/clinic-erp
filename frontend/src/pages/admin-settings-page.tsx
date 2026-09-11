import { zodResolver } from '@hookform/resolvers/zod'
import { Building2, FlaskConical, Pill, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { BranchFormDialog } from '@/components/admin/branch-form-dialog'
import { PermissionOverrideDialog } from '@/components/admin/permission-override-dialog'
import { ROLE_LABELS } from '@/components/staff/role-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useBranches, useUpdateBranch } from '@/features/branches/hooks'
import type { BranchSummary } from '@/features/branches/types'
import { useDeletePermissionOverride, usePermissionOverrides } from '@/features/permissions/hooks'
import { useClinicSettings, useMyClinic, useUpdateClinic, useUpsertClinicSetting } from '@/features/tenancy/hooks'
import { getErrorMessage } from '@/lib/errors'

const clinicProfileSchema = z.object({
  name: z.string().min(1, 'Name is required').max(200),
  gst_number: z.string().max(20).optional().or(z.literal('')),
})
type ClinicProfileValues = z.infer<typeof clinicProfileSchema>

// The three optional modules gated by a `features.<x>_enabled` TenantSetting
// (require_feature_flag, backend/app/api/deps.py) — toggled here via the
// existing generic PUT/DELETE .../settings/{key} endpoints, no dedicated
// toggle endpoint needed. Unset (no row at all) reads as off, same as a
// row explicitly set to false — deleting the key and setting it false are
// equivalent, but this UI always writes an explicit boolean for clarity.
const FEATURE_FLAGS = [
  { key: 'features.lab_enabled', label: 'Pathology / Diagnostic Lab', icon: FlaskConical, description: 'Lab test catalog, sample collection, and result entry.' },
  { key: 'features.pharmacy_enabled', label: 'Pharmacy OTC / Retail Sales', icon: Pill, description: 'Counter checkout against the medicine catalog (dispensing against a prescription is always on).' },
  { key: 'features.abdm_enabled', label: 'ABHA / ABDM Preparedness', icon: ShieldCheck, description: 'Allows recording a patient’s ABHA ID / address.' },
] as const

function FeatureFlagsCard() {
  const { data: settings, isLoading } = useClinicSettings()
  const upsertSetting = useUpsertClinicSetting()

  function isEnabled(key: string): boolean {
    return settings?.find((s) => s.key === key)?.value === true
  }

  async function toggle(key: string, next: boolean) {
    try {
      await upsertSetting.mutateAsync({ key, value: next })
      toast.success(`${next ? 'Enabled' : 'Disabled'} ${key}`)
    } catch (error) {
      toast.error('Could not update setting', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Feature flags</CardTitle>
        <CardDescription>Optional modules, off by default for a new clinic.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {isLoading && Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        {!isLoading &&
          FEATURE_FLAGS.map((flag) => (
            <label key={flag.key} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <Checkbox checked={isEnabled(flag.key)} onCheckedChange={(checked) => void toggle(flag.key, checked === true)} className="mt-0.5" />
              <div className="flex flex-col gap-0.5">
                <span className="flex items-center gap-1.5 text-sm font-medium text-slate-900 dark:text-slate-100">
                  <flag.icon className="size-3.5 text-slate-400" />
                  {flag.label}
                </span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{flag.description}</span>
              </div>
            </label>
          ))}
      </CardContent>
    </Card>
  )
}

function ClinicProfileCard() {
  const { data: clinic, isLoading } = useMyClinic()
  const updateClinic = useUpdateClinic()
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ClinicProfileValues>({ resolver: zodResolver(clinicProfileSchema), defaultValues: { name: '', gst_number: '' } })

  useEffect(() => {
    if (clinic) reset({ name: clinic.name, gst_number: clinic.gst_number ?? '' })
  }, [clinic, reset])

  async function onSubmit(values: ClinicProfileValues) {
    try {
      await updateClinic.mutateAsync({ name: values.name, gst_number: values.gst_number || null })
      toast.success('Clinic profile updated')
    } catch (error) {
      toast.error('Could not update clinic', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Clinic profile</CardTitle>
        <CardDescription>{clinic ? `Slug: ${clinic.slug} · ${clinic.timezone} · ${clinic.locale}` : 'Loading…'}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-48" />
          </div>
        ) : (
          <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="clinicName">Clinic name *</Label>
                <Input id="clinicName" {...register('name')} />
                {errors.name && <p className="text-sm text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="gstNumber">GSTIN</Label>
                <Input id="gstNumber" placeholder="15-character GSTIN" {...register('gst_number')} />
                {errors.gst_number && <p className="text-sm text-destructive">{errors.gst_number.message}</p>}
              </div>
            </div>
            <div>
              <Button type="submit" disabled={isSubmitting || !isDirty} size="sm">
                {isSubmitting ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

function BranchesCard() {
  const { data: branches, isLoading } = useBranches()
  const updateBranch = useUpdateBranch()
  const [formOpen, setFormOpen] = useState(false)
  const [editingBranch, setEditingBranch] = useState<BranchSummary | null>(null)

  async function toggleActive(branch: BranchSummary) {
    try {
      await updateBranch.mutateAsync({ branchId: branch.id, payload: { is_active: !branch.is_active } })
      toast.success(branch.is_active ? 'Branch deactivated' : 'Branch activated')
    } catch (error) {
      toast.error('Could not update branch', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Branches</CardTitle>
          <CardDescription>Every role that schedules, checks in, or dispenses needs at least one active branch.</CardDescription>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          onClick={() => {
            setEditingBranch(null)
            setFormOpen(true)
          }}
        >
          <Plus className="size-3.5" />
          Add branch
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Address</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 2 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 5 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {!isLoading && (branches ?? []).length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5} className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
                  No branches yet.
                </TableCell>
              </TableRow>
            )}
            {!isLoading &&
              (branches ?? []).map((branch) => (
                <TableRow key={branch.id}>
                  <TableCell className="font-medium text-slate-900 dark:text-slate-100">
                    <span className="flex items-center gap-1.5">
                      <Building2 className="size-3.5 text-slate-400" />
                      {branch.name}
                    </span>
                  </TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{branch.address || '—'}</TableCell>
                  <TableCell className="text-slate-600 dark:text-slate-400">{branch.phone || '—'}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={branch.is_active ? 'text-emerald-600' : 'text-slate-500'}>
                      {branch.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingBranch(branch)
                        setFormOpen(true)
                      }}
                    >
                      Edit
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => void toggleActive(branch)}>
                      {branch.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </CardContent>
      <BranchFormDialog branch={editingBranch} open={formOpen} onOpenChange={setFormOpen} />
    </Card>
  )
}

function PermissionOverridesCard() {
  const { data, isLoading } = usePermissionOverrides()
  const deleteOverride = useDeletePermissionOverride()
  const [dialogOpen, setDialogOpen] = useState(false)

  async function handleDelete(id: string) {
    try {
      await deleteOverride.mutateAsync(id)
      toast.success('Override removed')
    } catch (error) {
      toast.error('Could not remove override', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>Permission overrides</CardTitle>
          <CardDescription>Grant or revoke one permission for a role at this clinic, without a code change (PRD §13).</CardDescription>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setDialogOpen(true)}>
          <Plus className="size-3.5" />
          Add override
        </Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Target</TableHead>
              <TableHead>Permission</TableHead>
              <TableHead>Effect</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 2 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 4 }).map((__, j) => (
                    <TableCell key={j}>
                      <Skeleton className="h-4 w-full max-w-24" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {!isLoading && (data?.items ?? []).length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={4} className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
                  No overrides configured — every role uses its default permission set.
                </TableCell>
              </TableRow>
            )}
            {!isLoading &&
              (data?.items ?? []).map((override) => (
                <TableRow key={override.id}>
                  <TableCell className="text-slate-700 dark:text-slate-300">
                    {override.role_code ? (ROLE_LABELS[override.role_code] ?? override.role_code) : override.user_id}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-700 dark:text-slate-300">{override.permission_code}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={override.granted ? 'text-emerald-600' : 'text-red-600'}>
                      {override.granted ? 'Granted' : 'Revoked'}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" className="gap-1 text-red-600 hover:text-red-700" onClick={() => void handleDelete(override.id)}>
                      <Trash2 className="size-3.5" />
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </CardContent>
      <PermissionOverrideDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </Card>
  )
}

export function AdminSettingsPage() {
  const { hasPermission } = useAuth()

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Clinic settings</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Owner-only administration: profile, feature flags, branches, and permission overrides.</p>
      </div>

      <ClinicProfileCard />
      <FeatureFlagsCard />
      <BranchesCard />
      {hasPermission('staff.manage') && <PermissionOverridesCard />}
    </div>
  )
}
