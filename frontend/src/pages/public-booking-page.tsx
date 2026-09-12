import { zodResolver } from '@hookform/resolvers/zod'
import { CalendarClock, CheckCircle2, HeartPulse, RefreshCcw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  useBookPublicAppointment,
  usePublicBranches,
  usePublicClinic,
  usePublicDoctors,
  usePublicSlots,
  useRetryPublicPayment,
} from '@/features/public-booking/hooks'
import type { PublicBookingResponse } from '@/features/public-booking/types'
import { getErrorMessage } from '@/lib/errors'
import { formatDateInput } from '@/lib/working-hours'
import { PHONE_PATTERN } from '@/lib/validation'

const patientDetailsSchema = z.object({
  first_name: z.string().min(1, 'First name is required').max(100),
  last_name: z.string().max(100).optional().or(z.literal('')),
  phone: z.string().regex(PHONE_PATTERN, 'Enter a valid phone number'),
  email: z.string().email('Enter a valid email address').optional().or(z.literal('')),
  request_prepayment: z.boolean(),
  prepayment_amount: z.string().optional().or(z.literal('')),
})
type PatientDetailsValues = z.infer<typeof patientDetailsSchema>

function formatSlotLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export function PublicBookingPage() {
  const { clinicSlug } = useParams<{ clinicSlug: string }>()
  const [branchId, setBranchId] = useState('')
  const [doctorId, setDoctorId] = useState('')
  const [dateValue, setDateValue] = useState(() => formatDateInput(new Date(Date.now() + 24 * 60 * 60 * 1000)))
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null)
  const [booked, setBooked] = useState<PublicBookingResponse | null>(null)

  const clinicQuery = usePublicClinic(clinicSlug)
  const branchesQuery = usePublicBranches(clinicSlug)
  const doctorsQuery = usePublicDoctors(clinicSlug, branchId || undefined)
  const slotsQuery = usePublicSlots(clinicSlug, doctorId || undefined, doctorId ? dateValue : undefined)
  const bookMutation = useBookPublicAppointment(clinicSlug ?? '')
  const retryMutation = useRetryPublicPayment(clinicSlug ?? '')

  const branchSelectItems = useMemo(
    () => Object.fromEntries((branchesQuery.data ?? []).map((b) => [b.id, b.name])),
    [branchesQuery.data],
  )
  const doctorSelectItems = useMemo(
    () =>
      Object.fromEntries(
        (doctorsQuery.data ?? []).map((d) => [
          d.user_id,
          [d.first_name, d.last_name].filter(Boolean).join(' ') + (d.specialization ? ` — ${d.specialization}` : ''),
        ]),
      ),
    [doctorsQuery.data],
  )

  const {
    register,
    handleSubmit,
    watch,
    control,
    formState: { errors, isSubmitting },
  } = useForm<PatientDetailsValues>({
    resolver: zodResolver(patientDetailsSchema),
    defaultValues: { first_name: '', last_name: '', phone: '', email: '', request_prepayment: false, prepayment_amount: '' },
  })
  const requestPrepayment = watch('request_prepayment')

  if (!clinicSlug) return null

  if (clinicQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-900">
        <p className="text-sm text-muted-foreground">Clinic not found. Check the link and try again.</p>
      </div>
    )
  }

  async function onSubmit(values: PatientDetailsValues) {
    if (!doctorId || !branchId || !selectedSlot) {
      toast.error('Pick a branch, doctor, and time slot first')
      return
    }
    try {
      const result = await bookMutation.mutateAsync({
        branch_id: branchId,
        doctor_id: doctorId,
        scheduled_at: selectedSlot,
        first_name: values.first_name,
        last_name: values.last_name || undefined,
        phone: values.phone,
        email: values.email || undefined,
        request_prepayment: values.request_prepayment,
        prepayment_amount: values.request_prepayment ? values.prepayment_amount || undefined : undefined,
      })
      setBooked(result)
      toast.success('Appointment booked')
    } catch (error) {
      toast.error('Could not book this appointment', { description: getErrorMessage(error) })
    }
  }

  async function onRetryPayment(phone: string) {
    if (!booked) return
    try {
      const order = await retryMutation.mutateAsync({ appointmentId: booked.appointment_id, payload: { phone } })
      toast.success('New payment order created', { description: `Order ${order.order_id}` })
    } catch (error) {
      toast.error('Could not retry payment', { description: getErrorMessage(error) })
    }
  }

  return (
    <div className="flex min-h-screen justify-center bg-slate-50 p-4 dark:bg-slate-900">
      <div className="flex w-full max-w-xl flex-col gap-6 py-8">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
            <HeartPulse className="size-5" />
          </div>
          <div>
            <p className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-50">
              {clinicQuery.data?.name ?? 'Book an appointment'}
            </p>
            <p className="text-xs text-muted-foreground">No account needed — book in a few steps.</p>
          </div>
        </div>

        {booked ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="size-5 text-emerald-600" />
                Booking confirmed
              </CardTitle>
              <CardDescription>
                {new Date(booked.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <p>
                Status: <span className="font-medium">{booked.status}</span> · Payment:{' '}
                <span className="font-medium">{booked.payment_status}</span>
              </p>
              {booked.gateway_order && (
                <div className="rounded-md border border-border p-3">
                  <p className="font-medium">Online prepayment order created</p>
                  <p className="text-xs text-muted-foreground">
                    Provider: {booked.gateway_order.provider} · Order {booked.gateway_order.order_id} · ₹{booked.gateway_order.amount}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Complete payment through the clinic's checkout to confirm this booking. If it fails or expires, use
                    Retry below with the phone number you booked with.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2 gap-1.5"
                    disabled={retryMutation.isPending}
                    onClick={() => onRetryPayment(watch('phone'))}
                  >
                    <RefreshCcw className="size-3.5" />
                    Retry payment
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <CalendarClock className="size-4" />
                  1. Choose branch and doctor
                </CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(branchesQuery.data?.length ?? 0) > 1 && (
                  <div className="flex flex-col gap-1.5">
                    <Label>Branch</Label>
                    <Select value={branchId} onValueChange={(v) => v && setBranchId(v)}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Select branch" />
                      </SelectTrigger>
                      <SelectContent>
                        {(branchesQuery.data ?? []).map((b) => (
                          <SelectItem key={b.id} value={b.id}>
                            {branchSelectItems[b.id]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="flex flex-col gap-1.5">
                  <Label>Doctor</Label>
                  <Select value={doctorId} onValueChange={(v) => { setDoctorId(v ?? ''); setSelectedSlot(null) }}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select doctor" />
                    </SelectTrigger>
                    <SelectContent>
                      {(doctorsQuery.data ?? []).map((d) => (
                        <SelectItem key={d.user_id} value={d.user_id}>
                          {doctorSelectItems[d.user_id]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>

            {doctorId && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">2. Pick a time</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <Input
                    type="date"
                    value={dateValue}
                    min={formatDateInput(new Date())}
                    onChange={(e) => { setDateValue(e.target.value); setSelectedSlot(null) }}
                    className="w-full sm:w-48"
                  />
                  <div className="flex flex-wrap gap-2">
                    {slotsQuery.isLoading && <p className="text-sm text-muted-foreground">Loading slots…</p>}
                    {!slotsQuery.isLoading && (slotsQuery.data?.slots.length ?? 0) === 0 && (
                      <p className="text-sm text-muted-foreground">No available slots on this date.</p>
                    )}
                    {(slotsQuery.data?.slots ?? []).map((slot) => (
                      <Button
                        key={slot.scheduled_at}
                        type="button"
                        variant={selectedSlot === slot.scheduled_at ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setSelectedSlot(slot.scheduled_at)}
                      >
                        {formatSlotLabel(slot.scheduled_at)}
                      </Button>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {selectedSlot && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">3. Your details</CardTitle>
                  <CardDescription>First time here? We'll create your patient record automatically.</CardDescription>
                </CardHeader>
                <CardContent>
                  <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="bookingFirstName">First name *</Label>
                        <Input id="bookingFirstName" {...register('first_name')} />
                        {errors.first_name && <p className="text-sm text-destructive">{errors.first_name.message}</p>}
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="bookingLastName">Last name</Label>
                        <Input id="bookingLastName" {...register('last_name')} />
                      </div>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="bookingPhone">Phone *</Label>
                        <Input id="bookingPhone" type="tel" {...register('phone')} />
                        {errors.phone && <p className="text-sm text-destructive">{errors.phone.message}</p>}
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="bookingEmail">Email</Label>
                        <Input id="bookingEmail" type="email" {...register('email')} />
                        {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Controller
                        control={control}
                        name="request_prepayment"
                        render={({ field }) => (
                          <Checkbox id="requestPrepayment" checked={field.value} onCheckedChange={field.onChange} />
                        )}
                      />
                      <Label htmlFor="requestPrepayment" className="font-normal">
                        Pay online now to secure this slot
                      </Label>
                    </div>
                    {requestPrepayment && (
                      <div className="flex flex-col gap-1.5">
                        <Label htmlFor="prepaymentAmount">Amount (₹)</Label>
                        <Input id="prepaymentAmount" type="number" min={1} step="0.01" {...register('prepayment_amount')} />
                      </div>
                    )}

                    <Button type="submit" disabled={isSubmitting || bookMutation.isPending} className="mt-2">
                      {bookMutation.isPending ? 'Booking…' : 'Confirm booking'}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  )
}
