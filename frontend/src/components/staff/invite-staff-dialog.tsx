import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { ROLE_LABELS, RoleBadge } from '@/components/staff/role-badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useCreateDoctor } from '@/features/doctors/hooks'
import { STAFF_ROLE_CODES, type StaffRoleCode } from '@/features/staff/types'
import { useCreateStaff } from '@/features/staff/hooks'
import { getErrorMessage } from '@/lib/errors'
import { PHONE_PATTERN } from '@/lib/validation'

const INVITABLE_ROLES = ['DOCTOR', ...STAFF_ROLE_CODES] as const
type InvitableRole = (typeof INVITABLE_ROLES)[number]

const inviteFormSchema = z
  .object({
    roleCode: z.enum(INVITABLE_ROLES),
    first_name: z.string().min(1, 'First name is required').max(100),
    last_name: z.string().max(100).optional().or(z.literal('')),
    email: z.string().email('Enter a valid email address').optional().or(z.literal('')),
    phone: z.string().regex(PHONE_PATTERN, 'Enter a valid phone number').optional().or(z.literal('')),
    designation: z.string().max(200).optional().or(z.literal('')),
    specialization: z.string().max(200).optional().or(z.literal('')),
    registrationNumber: z.string().max(100).optional().or(z.literal('')),
    consultationFee: z
      .string()
      .optional()
      .or(z.literal(''))
      .refine((v) => !v || Number(v) >= 0, 'Must be a positive number'),
  })
  .refine((data) => data.email || data.phone, {
    message: 'Provide an email address or a phone number',
    path: ['email'],
  })

type InviteFormValues = z.infer<typeof inviteFormSchema>

const DEFAULT_VALUES: InviteFormValues = {
  roleCode: 'RECEPTIONIST',
  first_name: '',
  last_name: '',
  email: '',
  phone: '',
  designation: '',
  specialization: '',
  registrationNumber: '',
  consultationFee: '',
}

interface InviteSuccess {
  name: string
  roleCode: InvitableRole
  expiresAt: string | null
  debugToken: string | null
  temporaryPassword: string | null
}

export function InviteStaffDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const createStaff = useCreateStaff()
  const createDoctor = useCreateDoctor()
  const [success, setSuccess] = useState<InviteSuccess | null>(null)

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteFormValues>({ resolver: zodResolver(inviteFormSchema), defaultValues: DEFAULT_VALUES })

  const roleCode = watch('roleCode')
  const isDoctor = roleCode === 'DOCTOR'

  useEffect(() => {
    if (!open) {
      reset(DEFAULT_VALUES)
      setSuccess(null)
    }
  }, [open, reset])

  async function onSubmit(values: InviteFormValues) {
    try {
      if (values.roleCode === 'DOCTOR') {
        const created = await createDoctor.mutateAsync({
          first_name: values.first_name,
          last_name: values.last_name || undefined,
          email: values.email || undefined,
          phone: values.phone || undefined,
          specialization: values.specialization || undefined,
          registration_number: values.registrationNumber || undefined,
          consultation_fee: values.consultationFee ? Number(values.consultationFee) : undefined,
        })
        setSuccess({
          name: [created.doctor.first_name, created.doctor.last_name].filter(Boolean).join(' '),
          roleCode: 'DOCTOR',
          expiresAt: created.invite.invite_expires_at,
          debugToken: created.invite.debug_invite_token,
          temporaryPassword: created.invite.temporary_password,
        })
      } else {
        const created = await createStaff.mutateAsync({
          role_code: values.roleCode as StaffRoleCode,
          first_name: values.first_name,
          last_name: values.last_name || undefined,
          email: values.email || undefined,
          phone: values.phone || undefined,
          designation: values.designation || undefined,
        })
        setSuccess({
          name: [created.staff.first_name, created.staff.last_name].filter(Boolean).join(' '),
          roleCode: values.roleCode,
          expiresAt: created.invite.invite_expires_at,
          debugToken: created.invite.debug_invite_token,
          temporaryPassword: created.invite.temporary_password,
        })
      }
      toast.success('Invite created')
    } catch (error) {
      toast.error('Could not create invite', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {success ? (
          <>
            <DialogHeader>
              <DialogTitle>{success.temporaryPassword ? 'Account created' : 'Invite created'}</DialogTitle>
              <DialogDescription>
                {success.name} (<RoleBadge roleCode={success.roleCode} />){' '}
                {success.temporaryPassword
                  ? 'is active now.'
                  : `has been invited. The invite expires ${success.expiresAt ? new Date(success.expiresAt).toLocaleString() : ''}.`}
              </DialogDescription>
            </DialogHeader>
            {success.temporaryPassword && (
              <div className="flex flex-col gap-1.5">
                <Label>Temporary password — shown once</Label>
                <p className="text-xs text-muted-foreground">
                  No real email/SMS provider is configured yet — share this password with them directly (e.g. by
                  phone or in person). It's never shown again after you close this dialog.
                </p>
                <Input readOnly value={success.temporaryPassword} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
              </div>
            )}
            {success.debugToken && (
              <div className="flex flex-col gap-1.5">
                <Label>Dev-only invite token</Label>
                <p className="text-xs text-muted-foreground">
                  No real email/SMS provider is configured yet — share this token manually so they can accept the
                  invite via clinic slug + this token.
                </p>
                <Input readOnly value={success.debugToken} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
              </div>
            )}
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>Done</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Invite staff member</DialogTitle>
              <DialogDescription>They'll receive a one-time invite to set their password.</DialogDescription>
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
                        {INVITABLE_ROLES.map((role) => (
                          <SelectItem key={role} value={role}>
                            {ROLE_LABELS[role]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="first_name">First name *</Label>
                  <Input id="first_name" {...register('first_name')} />
                  {errors.first_name && <p className="text-sm text-destructive">{errors.first_name.message}</p>}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="last_name">Last name</Label>
                  <Input id="last_name" {...register('last_name')} />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" {...register('email')} />
                  {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="phone">Phone</Label>
                  <Input id="phone" type="tel" {...register('phone')} />
                  {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
                </div>
              </div>

              {isDoctor ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="specialization">Specialization</Label>
                    <Input id="specialization" {...register('specialization')} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="registrationNumber">Registration no.</Label>
                    <Input id="registrationNumber" {...register('registrationNumber')} />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="consultationFee">Consultation fee</Label>
                    <Input id="consultationFee" type="number" min={0} step="0.01" {...register('consultationFee')} />
                    {errors.consultationFee && (
                      <p className="text-sm text-destructive">{errors.consultationFee.message}</p>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="designation">Designation</Label>
                  <Input id="designation" placeholder="e.g. Front Desk Lead" {...register('designation')} />
                </div>
              )}

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Inviting…' : 'Send invite'}
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
