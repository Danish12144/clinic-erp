import type { WorkingHours } from '@/features/doctors/types'

// backend/app/modules/appointments/service.py indexes WorkingHours by
// Python's datetime.weekday() (Mon=0..Sun=6) — JS Date.getDay() is
// Sun=0..Sat=6, a different scheme. This array is indexed by JS getDay().
const WEEKDAY_CODES_BY_JS_DAY = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'] as const

export function dayHoursFor(workingHours: WorkingHours, date: Date) {
  const code = WEEKDAY_CODES_BY_JS_DAY[date.getDay()]
  return workingHours[code] ?? null
}

function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export interface TimeSlot {
  minutesFromMidnight: number
  label: string
}

// A slot grid preview only — backend/app/modules/appointments/service.py's
// _validate_slot is the real source of truth at booking time (this can't
// perfectly replicate it, e.g. it doesn't know about a doctor's status or
// branch validity). Purely for UX: showing staff which times are worth
// trying.
export function generateTimeSlots(open: string, close: string, incrementMinutes: number): TimeSlot[] {
  const slots: TimeSlot[] = []
  const openMin = toMinutes(open)
  const closeMin = toMinutes(close)
  for (let t = openMin; t + incrementMinutes <= closeMin; t += incrementMinutes) {
    const h = Math.floor(t / 60)
    const m = t % 60
    const label = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
    slots.push({ minutesFromMidnight: t, label })
  }
  return slots
}

export function slotToDate(baseDate: Date, minutesFromMidnight: number): Date {
  const result = new Date(baseDate)
  result.setHours(0, 0, 0, 0)
  result.setMinutes(minutesFromMidnight)
  return result
}

export function formatDateInput(date: Date): string {
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}
