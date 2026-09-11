import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { ROLE_LABELS } from '@/components/staff/role-badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useSetPermissionOverride } from '@/features/permissions/hooks'
import { getErrorMessage } from '@/lib/errors'

// The role a permission_override targets — every system role except
// PATIENT, which never authenticates as staff and so has no role-level
// permission grants to override (backend/app/modules/auth/models.py's
// 8-role model; PATIENT is excluded here the same way STAFF_ROLE_CODES
// excludes it for staff provisioning).
const OVERRIDABLE_ROLES = ['OWNER', 'DOCTOR', 'RECEPTIONIST', 'NURSE', 'LAB_STAFF', 'PHARMACY_STAFF', 'OTHER_STAFF'] as const

const overrideFormSchema = z.object({
  roleCode: z.enum(OVERRIDABLE_ROLES),
  permissionCode: z.string().min(1, 'Permission code is required').max(100),
  granted: z.boolean(),
})

type OverrideFormValues = z.infer<typeof overrideFormSchema>

const DEFAULT_VALUES: OverrideFormValues = { roleCode: 'RECEPTIONIST', permissionCode: '', granted: true }

// A starting set of permission codes an Owner is likely to want to
// override per-role — not exhaustive (permission_code is free text on
// the backend, any real code works), just autocomplete hints for the
// PRD §13 flagship example (vitals.record for Receptionist) and a few
// other commonly-configurable ones.
const COMMON_PERMISSION_CODES = [
  'vitals.record',
  'vitals.view',
  'checkin.manage',
  'queue.manage',
  'appointments.manage',
  'pharmacy.sell_otc',
  'inventory.record_usage',
  'expenses.record',
]

export function PermissionOverrideDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const setOverride = useSetPermissionOverride()

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<OverrideFormValues>({ resolver: zodResolver(overrideFormSchema), defaultValues: DEFAULT_VALUES })

  useEffect(() => {
    if (open) reset(DEFAULT_VALUES)
  }, [open, reset])

  async function onSubmit(values: OverrideFormValues) {
    try {
      await setOverride.mutateAsync({ role_code: values.roleCode, permission_code: values.permissionCode.trim(), granted: values.granted })
      toast.success('Permission override saved')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not save override', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add permission override</DialogTitle>
          <DialogDescription>
            Grants or revokes one permission for every user with the selected role, at this clinic only — takes
            effect on their next login/token refresh.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="flex flex-col gap-1.5">
            <Label>Role</Label>
            <Controller
              control={control}
              name="roleCode"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OVERRIDABLE_ROLES.map((role) => (
                      <SelectItem key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="permissionCode">Permission code *</Label>
            <Input id="permissionCode" list="common-permission-codes" placeholder="e.g. vitals.record" {...register('permissionCode')} />
            <datalist id="common-permission-codes">
              {COMMON_PERMISSION_CODES.map((code) => (
                <option key={code} value={code} />
              ))}
            </datalist>
            {errors.permissionCode && <p className="text-sm text-destructive">{errors.permissionCode.message}</p>}
          </div>

          <div className="flex items-center gap-2">
            <Controller control={control} name="granted" render={({ field }) => <Checkbox id="granted" checked={field.value} onCheckedChange={field.onChange} />} />
            <Label htmlFor="granted" className="font-normal">
              Grant this permission (uncheck to revoke it)
            </Label>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
