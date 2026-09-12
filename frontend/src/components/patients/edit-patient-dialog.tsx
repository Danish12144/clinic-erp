import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { joinCommaList, splitCommaList } from '@/components/patients/new-patient-dialog'
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
import { Textarea } from '@/components/ui/textarea'
import { useUpdatePatient } from '@/features/patients/hooks'
import type { BloodGroup, PatientSummary } from '@/features/patients/types'
import { getErrorMessage } from '@/lib/errors'
import { PHONE_PATTERN } from '@/lib/validation'

const BLOOD_GROUPS: BloodGroup[] = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']

const editPatientFormSchema = z.object({
  first_name: z.string().min(1, 'First name is required').max(100),
  last_name: z.string().max(100).optional().or(z.literal('')),
  gender: z.enum(['Male', 'Female', 'Other']).optional(),
  date_of_birth: z.string().optional().or(z.literal('')),
  phone: z.string().regex(PHONE_PATTERN, 'Enter a valid phone number').optional().or(z.literal('')),
  email: z.string().email('Enter a valid email address').optional().or(z.literal('')),
  bloodGroup: z.enum(BLOOD_GROUPS as [BloodGroup, ...BloodGroup[]]).optional(),
  address: z.string().max(500).optional().or(z.literal('')),
  allergies: z.string().optional().or(z.literal('')),
  chronicConditions: z.string().optional().or(z.literal('')),
})

type EditPatientFormValues = z.infer<typeof editPatientFormSchema>

function toFormValues(patient: PatientSummary): EditPatientFormValues {
  return {
    first_name: patient.first_name,
    last_name: patient.last_name ?? '',
    gender: patient.gender ?? undefined,
    date_of_birth: patient.date_of_birth ?? '',
    phone: patient.phone ?? '',
    email: patient.email ?? '',
    bloodGroup: patient.blood_group ?? undefined,
    address: patient.address ?? '',
    allergies: joinCommaList(patient.allergies),
    chronicConditions: joinCommaList(patient.chronic_conditions),
  }
}

export function EditPatientDialog({
  patient,
  open,
  onOpenChange,
}: {
  patient: PatientSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const updatePatient = useUpdatePatient()

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<EditPatientFormValues>({
    resolver: zodResolver(editPatientFormSchema),
    defaultValues: patient ? toFormValues(patient) : undefined,
  })

  useEffect(() => {
    if (patient && open) reset(toFormValues(patient))
  }, [patient, open, reset])

  async function onSubmit(values: EditPatientFormValues) {
    if (!patient) return
    try {
      await updatePatient.mutateAsync({
        patientId: patient.id,
        payload: {
          first_name: values.first_name,
          last_name: values.last_name || null,
          gender: values.gender ?? null,
          date_of_birth: values.date_of_birth || null,
          phone: values.phone || null,
          email: values.email || null,
          blood_group: values.bloodGroup ?? null,
          address: values.address || null,
          allergies: values.allergies ? splitCommaList(values.allergies) : [],
          chronic_conditions: values.chronicConditions ? splitCommaList(values.chronicConditions) : [],
        },
      })
      toast.success('Patient updated')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not update patient', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] sm:max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit patient</DialogTitle>
          <DialogDescription>MRN {patient?.mrn}</DialogDescription>
        </DialogHeader>

        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_first_name">First name *</Label>
              <Input id="edit_first_name" {...register('first_name')} />
              {errors.first_name && <p className="text-sm text-destructive">{errors.first_name.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_last_name">Last name</Label>
              <Input id="edit_last_name" {...register('last_name')} />
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
              <Label htmlFor="edit_date_of_birth">Date of birth</Label>
              <Input id="edit_date_of_birth" type="date" {...register('date_of_birth')} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Blood group</Label>
              <Controller
                control={control}
                name="bloodGroup"
                render={({ field }) => (
                  <Select value={field.value ?? ''} onValueChange={(value) => field.onChange(value || undefined)}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      {BLOOD_GROUPS.map((bg) => (
                        <SelectItem key={bg} value={bg}>
                          {bg}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_phone">Phone</Label>
              <Input id="edit_phone" type="tel" {...register('phone')} />
              {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_email">Email</Label>
              <Input id="edit_email" type="email" {...register('email')} />
              {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit_address">Address</Label>
            <Textarea id="edit_address" rows={2} {...register('address')} />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_allergies">Allergies</Label>
              <Input id="edit_allergies" placeholder="e.g. Penicillin, Peanuts" {...register('allergies')} />
              <p className="text-xs text-muted-foreground">Comma-separated. Shown as a red alert during consultation.</p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit_chronicConditions">Chronic conditions</Label>
              <Input id="edit_chronicConditions" placeholder="e.g. Diabetes, Hypertension" {...register('chronicConditions')} />
              <p className="text-xs text-muted-foreground">Comma-separated.</p>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving…' : 'Save changes'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
