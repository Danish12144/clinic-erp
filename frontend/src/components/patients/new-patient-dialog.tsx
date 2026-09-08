import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import { Separator } from '@/components/ui/separator'
import { Textarea } from '@/components/ui/textarea'
import { useAuth } from '@/features/auth/auth-context'
import { useBranches } from '@/features/branches/hooks'
import { useRegisterWalkIn } from '@/features/checkin/hooks'
import { useDoctorDirectory } from '@/features/doctors/hooks'
import { useCreatePatient } from '@/features/patients/hooks'
import { getErrorMessage } from '@/lib/errors'
import { PHONE_PATTERN } from '@/lib/validation'

const patientFormSchema = z
  .object({
    first_name: z.string().min(1, 'First name is required').max(100),
    last_name: z.string().max(100).optional().or(z.literal('')),
    gender: z.enum(['Male', 'Female', 'Other']).optional(),
    date_of_birth: z.string().optional().or(z.literal('')),
    age: z
      .string()
      .optional()
      .or(z.literal(''))
      .refine((v) => !v || (Number(v) > 0 && Number(v) < 130), 'Enter a plausible age'),
    phone: z.string().regex(PHONE_PATTERN, 'Enter a valid phone number').optional().or(z.literal('')),
    email: z.string().email('Enter a valid email address').optional().or(z.literal('')),
    address: z.string().max(500).optional().or(z.literal('')),
    abhaId: z.string().max(20).optional().or(z.literal('')),
    abhaAddress: z.string().max(100).optional().or(z.literal('')),
    checkInNow: z.boolean(),
    branchId: z.string().optional().or(z.literal('')),
    doctorId: z.string().optional().or(z.literal('')),
  })
  .refine((data) => data.phone || data.email, {
    message: 'Provide a phone number or email address',
    path: ['phone'],
  })
  .refine((data) => !data.checkInNow || data.branchId, {
    message: 'Select a branch to check in',
    path: ['branchId'],
  })

type PatientFormValues = z.infer<typeof patientFormSchema>

const DEFAULT_VALUES: PatientFormValues = {
  first_name: '',
  last_name: '',
  gender: undefined,
  date_of_birth: '',
  age: '',
  phone: '',
  email: '',
  address: '',
  abhaId: '',
  abhaAddress: '',
  checkInNow: true,
  branchId: '',
  doctorId: '',
}

// Many walk-in patients don't know their exact date of birth — Age is a
// convenience-only input that resolves to an approximate DOB (Jan 1 of the
// birth year) on submit; the backend only ever accepts date_of_birth.
function resolveDateOfBirth(values: PatientFormValues): string | undefined {
  if (values.date_of_birth) return values.date_of_birth
  if (values.age) {
    const birthYear = new Date().getFullYear() - Number(values.age)
    return `${birthYear}-01-01`
  }
  return undefined
}

export function NewPatientDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { hasPermission } = useAuth()
  const canCheckIn = hasPermission('checkin.manage')
  const { data: branches } = useBranches()
  const { data: directory } = useDoctorDirectory()
  const createPatient = useCreatePatient()
  const registerWalkIn = useRegisterWalkIn()
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    control,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PatientFormValues>({ resolver: zodResolver(patientFormSchema), defaultValues: DEFAULT_VALUES })

  const checkInNow = watch('checkInNow')

  // Single-branch clinics (the common case) shouldn't have to pick one —
  // auto-select it as soon as the list loads.
  useEffect(() => {
    if (branches?.length === 1 && open) {
      reset((current) => ({ ...current, branchId: branches[0].id }))
    }
  }, [branches, open, reset])

  useEffect(() => {
    if (!open) {
      reset(DEFAULT_VALUES)
      setDuplicateWarning(null)
    }
  }, [open, reset])

  async function onSubmit(values: PatientFormValues) {
    setDuplicateWarning(null)
    try {
      const created = await createPatient.mutateAsync({
        first_name: values.first_name,
        last_name: values.last_name || undefined,
        gender: values.gender,
        date_of_birth: resolveDateOfBirth(values),
        phone: values.phone || undefined,
        email: values.email || undefined,
        address: values.address || undefined,
        abha_id: values.abhaId || undefined,
        abha_address: values.abhaAddress || undefined,
      })

      const fullName = [created.patient.first_name, created.patient.last_name].filter(Boolean).join(' ')
      toast.success(`${fullName} registered`, { description: `MRN ${created.patient.mrn}` })

      const hasDuplicates = created.possible_duplicates.length > 0
      if (hasDuplicates) {
        setDuplicateWarning(
          `${created.possible_duplicates.length} possible duplicate record(s) share this phone or name+DOB. The new record was created anyway — review and merge manually if needed.`,
        )
      }

      if (values.checkInNow && values.branchId) {
        try {
          const result = await registerWalkIn.mutateAsync({
            patient_id: created.patient.id,
            branch_id: values.branchId,
            doctor_id: values.doctorId || undefined,
          })
          toast.success(`Checked in — token #${result.queue_token.token_number}`)
        } catch (checkInError) {
          toast.error('Patient registered, but check-in failed', { description: getErrorMessage(checkInError) })
        }
      }

      // Leave the dialog open (showing the duplicate warning) rather than
      // closing over unreviewed possible-duplicate matches.
      if (!hasDuplicates) {
        onOpenChange(false)
      }
    } catch (error) {
      toast.error('Could not register patient', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] sm:max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Register new patient</DialogTitle>
          <DialogDescription>MRN is generated automatically.</DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
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

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label>Gender</Label>
              <Controller
                control={control}
                name="gender"
                render={({ field }) => (
                  <Select value={field.value ?? ''} onValueChange={(value) => field.onChange(value || undefined)}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Male">Male</SelectItem>
                      <SelectItem value="Female">Female</SelectItem>
                      <SelectItem value="Other">Other</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="date_of_birth">Date of birth</Label>
              <Input id="date_of_birth" type="date" {...register('date_of_birth')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="age">Age (years)</Label>
              <Input id="age" type="number" min={0} max={129} placeholder="approx." {...register('age')} />
              {errors.age && <p className="text-sm text-destructive">{errors.age.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="phone">Phone</Label>
              <Input id="phone" type="tel" {...register('phone')} />
              {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" {...register('email')} />
              {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="address">Address</Label>
            <Textarea id="address" rows={2} {...register('address')} />
          </div>

          <details className="rounded-md border border-border p-3 text-sm">
            <summary className="cursor-pointer font-medium text-muted-foreground">
              Optional: ABHA (ABDM) details
            </summary>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="abhaId">ABHA number</Label>
                <Input id="abhaId" placeholder="14-digit ABHA number" {...register('abhaId')} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="abhaAddress">ABHA address</Label>
                <Input id="abhaAddress" placeholder="name@abdm" {...register('abhaAddress')} />
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Only saved if this clinic has ABDM enabled in settings.
            </p>
          </details>

          {canCheckIn && (
            <>
              <Separator />
              <div className="flex items-center gap-2">
                <Controller
                  control={control}
                  name="checkInNow"
                  render={({ field }) => (
                    <Checkbox id="checkInNow" checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <Label htmlFor="checkInNow" className="font-normal">
                  Check in now and issue a queue token
                </Label>
              </div>

              {checkInNow && (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex flex-col gap-1.5">
                    <Label>Branch *</Label>
                    <Controller
                      control={control}
                      name="branchId"
                      render={({ field }) => (
                        <Select value={field.value ?? ''} onValueChange={field.onChange}>
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
                      )}
                    />
                    {errors.branchId && <p className="text-sm text-destructive">{errors.branchId.message}</p>}
                  </div>
                  {directory && directory.items.length > 0 && (
                    <div className="flex flex-col gap-1.5">
                      <Label>Doctor (optional)</Label>
                      <Controller
                        control={control}
                        name="doctorId"
                        render={({ field }) => (
                          <Select value={field.value ?? ''} onValueChange={(value) => field.onChange(value || undefined)}>
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
                        )}
                      />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {duplicateWarning && (
            <p className="rounded-md bg-amber-100 p-2 text-sm text-amber-900 dark:bg-amber-500/15 dark:text-amber-300">
              {duplicateWarning}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Registering…' : 'Register patient'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
