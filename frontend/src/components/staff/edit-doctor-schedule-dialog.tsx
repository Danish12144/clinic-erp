import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
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
import { useBranches } from '@/features/branches/hooks'
import { useSetDoctorBranches, useUpdateDoctor } from '@/features/doctors/hooks'
import type { DoctorSummary, WorkingHours } from '@/features/doctors/types'
import { getErrorMessage } from '@/lib/errors'

const DAYS = [
  { code: 'mon', label: 'Monday' },
  { code: 'tue', label: 'Tuesday' },
  { code: 'wed', label: 'Wednesday' },
  { code: 'thu', label: 'Thursday' },
  { code: 'fri', label: 'Friday' },
  { code: 'sat', label: 'Saturday' },
  { code: 'sun', label: 'Sunday' },
] as const

type DayCode = (typeof DAYS)[number]['code']

interface DayRow {
  enabled: boolean
  open: string
  close: string
}

type DaySchedule = Record<DayCode, DayRow>

function scheduleFromWorkingHours(workingHours: WorkingHours): DaySchedule {
  const schedule = {} as DaySchedule
  for (const { code } of DAYS) {
    const hours = workingHours[code]
    schedule[code] = hours ? { enabled: true, open: hours.open, close: hours.close } : { enabled: false, open: '09:00', close: '18:00' }
  }
  return schedule
}

function scheduleToWorkingHours(schedule: DaySchedule): WorkingHours {
  const result: WorkingHours = {}
  for (const { code } of DAYS) {
    const row = schedule[code]
    if (row.enabled) result[code] = { open: row.open, close: row.close }
  }
  return result
}

export function EditDoctorScheduleDialog({
  doctor,
  open,
  onOpenChange,
}: {
  doctor: DoctorSummary | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const branchesQuery = useBranches()
  const updateDoctor = useUpdateDoctor()
  const setBranches = useSetDoctorBranches()

  const [schedule, setSchedule] = useState<DaySchedule>(() => scheduleFromWorkingHours({}))
  const [slotDuration, setSlotDuration] = useState('15')
  const [branchIds, setBranchIds] = useState<string[]>([])

  useEffect(() => {
    if (doctor && open) {
      setSchedule(scheduleFromWorkingHours(doctor.working_hours))
      setSlotDuration(String(doctor.slot_duration_minutes))
      setBranchIds(doctor.branch_ids)
    }
  }, [doctor, open])

  const doctorName = useMemo(
    () => (doctor ? [doctor.first_name, doctor.last_name].filter(Boolean).join(' ') || 'this doctor' : ''),
    [doctor],
  )

  const isSubmitting = updateDoctor.isPending || setBranches.isPending

  function toggleBranch(branchId: string, checked: boolean) {
    setBranchIds((prev) => (checked ? [...prev, branchId] : prev.filter((id) => id !== branchId)))
  }

  function updateDay(code: DayCode, patch: Partial<DayRow>) {
    setSchedule((prev) => ({ ...prev, [code]: { ...prev[code], ...patch } }))
  }

  async function onSubmit() {
    if (!doctor) return
    const slotDurationMinutes = Number(slotDuration)
    if (!Number.isFinite(slotDurationMinutes) || slotDurationMinutes < 5 || slotDurationMinutes > 240) {
      toast.error('Slot duration must be between 5 and 240 minutes')
      return
    }
    try {
      await updateDoctor.mutateAsync({
        userId: doctor.user_id,
        payload: { working_hours: scheduleToWorkingHours(schedule), slot_duration_minutes: slotDurationMinutes },
      })
      const sortedCurrent = [...doctor.branch_ids].sort()
      const sortedNext = [...branchIds].sort()
      if (JSON.stringify(sortedCurrent) !== JSON.stringify(sortedNext)) {
        await setBranches.mutateAsync({ userId: doctor.user_id, payload: { branch_ids: branchIds } })
      }
      toast.success('Schedule updated')
      onOpenChange(false)
    } catch (error) {
      toast.error('Could not update schedule', { description: getErrorMessage(error) })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit schedule — {doctorName}</DialogTitle>
          <DialogDescription>
            Set working hours per day, the slot grid increment used on the Appointments page, and which branches this
            doctor is assigned to.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 max-h-[60vh] overflow-y-auto pr-1">
          <div className="flex flex-col gap-2">
            <Label>Working hours</Label>
            {DAYS.map(({ code, label }) => (
              <div key={code} className="flex items-center gap-3">
                <Checkbox
                  id={`day-${code}`}
                  checked={schedule[code].enabled}
                  onCheckedChange={(checked) => updateDay(code, { enabled: checked === true })}
                />
                <Label htmlFor={`day-${code}`} className="w-24 font-normal">
                  {label}
                </Label>
                <Input
                  type="time"
                  value={schedule[code].open}
                  disabled={!schedule[code].enabled}
                  onChange={(event) => updateDay(code, { open: event.target.value })}
                  className="w-32"
                />
                <span className="text-sm text-muted-foreground">to</span>
                <Input
                  type="time"
                  value={schedule[code].close}
                  disabled={!schedule[code].enabled}
                  onChange={(event) => updateDay(code, { close: event.target.value })}
                  className="w-32"
                />
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="slotDuration">Appointment slot duration (minutes)</Label>
            <Input
              id="slotDuration"
              type="number"
              min={5}
              max={240}
              value={slotDuration}
              onChange={(event) => setSlotDuration(event.target.value)}
              className="w-32"
            />
            <p className="text-xs text-muted-foreground">
              How far apart the Appointments page offers bookable times for this doctor. Doesn't limit how long a
              specific appointment can be booked for.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Assigned branches</Label>
            {(branchesQuery.data ?? []).map((branch) => (
              <div key={branch.id} className="flex items-center gap-2">
                <Checkbox
                  id={`branch-${branch.id}`}
                  checked={branchIds.includes(branch.id)}
                  onCheckedChange={(checked) => toggleBranch(branch.id, checked === true)}
                />
                <Label htmlFor={`branch-${branch.id}`} className="font-normal">
                  {branch.name}
                </Label>
              </div>
            ))}
            {branchesQuery.data?.length === 0 && <p className="text-sm text-muted-foreground">No branches yet.</p>}
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : 'Save schedule'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
