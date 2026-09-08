import { zodResolver } from '@hookform/resolvers/zod'
import { Activity } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useEncounterVitals, useRecordVitals } from '@/features/vitals/hooks'
import { getErrorMessage } from '@/lib/errors'

const numericField = z
  .string()
  .optional()
  .or(z.literal(''))
  .refine((v) => !v || !Number.isNaN(Number(v)), 'Must be a number')

const vitalsFormSchema = z.object({
  systolic: numericField,
  diastolic: numericField,
  pulse: numericField,
  temperature: numericField,
  weight: numericField,
})

type VitalsFormValues = z.infer<typeof vitalsFormSchema>

export function VitalsPanel({ encounterId }: { encounterId: string }) {
  const { data } = useEncounterVitals(encounterId)
  const recordVitals = useRecordVitals()
  const [editing, setEditing] = useState(false)
  const latest = data?.items[0]

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<VitalsFormValues>({
    resolver: zodResolver(vitalsFormSchema),
    defaultValues: { systolic: '', diastolic: '', pulse: '', temperature: '', weight: '' },
  })

  async function onSubmit(values: VitalsFormValues) {
    if (!Object.values(values).some((v) => v)) {
      toast.error('Enter at least one reading')
      return
    }
    try {
      await recordVitals.mutateAsync({
        encounter_id: encounterId,
        systolic_bp: values.systolic ? Number(values.systolic) : undefined,
        diastolic_bp: values.diastolic ? Number(values.diastolic) : undefined,
        heart_rate: values.pulse ? Number(values.pulse) : undefined,
        temperature_celsius: values.temperature ? Number(values.temperature) : undefined,
        weight_kg: values.weight ? Number(values.weight) : undefined,
      })
      toast.success('Vitals recorded')
      reset()
      setEditing(false)
    } catch (error) {
      toast.error('Could not record vitals', { description: getErrorMessage(error) })
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-1.5 text-base">
          <Activity className="size-4" />
          Vitals
        </CardTitle>
        {latest && !editing && (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
            Add new reading
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {latest && !editing ? (
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">BP</dt>
              <dd className="font-medium">
                {latest.systolic_bp && latest.diastolic_bp ? `${latest.systolic_bp}/${latest.diastolic_bp}` : '—'}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Pulse</dt>
              <dd className="font-medium">{latest.heart_rate ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Temp (°C)</dt>
              <dd className="font-medium">{latest.temperature_celsius ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Weight (kg)</dt>
              <dd className="font-medium">{latest.weight_kg ?? '—'}</dd>
            </div>
          </dl>
        ) : (
          <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="systolic">BP systolic</Label>
                <Input id="systolic" inputMode="numeric" placeholder="120" {...register('systolic')} />
                {errors.systolic && <p className="text-xs text-destructive">{errors.systolic.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="diastolic">BP diastolic</Label>
                <Input id="diastolic" inputMode="numeric" placeholder="80" {...register('diastolic')} />
                {errors.diastolic && <p className="text-xs text-destructive">{errors.diastolic.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="pulse">Pulse</Label>
                <Input id="pulse" inputMode="numeric" placeholder="72" {...register('pulse')} />
                {errors.pulse && <p className="text-xs text-destructive">{errors.pulse.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="temperature">Temp (°C)</Label>
                <Input id="temperature" inputMode="decimal" placeholder="37.0" {...register('temperature')} />
                {errors.temperature && <p className="text-xs text-destructive">{errors.temperature.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="weight">Weight (kg)</Label>
                <Input id="weight" inputMode="decimal" placeholder="65" {...register('weight')} />
                {errors.weight && <p className="text-xs text-destructive">{errors.weight.message}</p>}
              </div>
            </div>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={isSubmitting}>
                {isSubmitting ? 'Saving…' : 'Save vitals'}
              </Button>
              {latest && (
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
