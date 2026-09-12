import { AlertTriangle, HeartPulse } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Phase 1 (Master Handoff §5 "CRITICAL — Safety") — surfaces
 * `Patient.allergies`/`chronic_conditions` (both have existed on the DB
 * and every read schema since migration 0004, but nothing outside the
 * demographics form ever rendered them) prominently wherever a clinician
 * is about to see or treat a patient: the OPD Consultation Pad and the
 * portal's own Medical Records timeline. Renders nothing at all when both
 * lists are empty, so it never adds visual noise to the common case.
 */
export function AllergyBanner({
  allergies,
  chronicConditions,
  className,
}: {
  allergies: string[]
  chronicConditions: string[]
  className?: string
}) {
  if (allergies.length === 0 && chronicConditions.length === 0) return null

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {allergies.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold tracking-wide uppercase">Allergies</span>
            <span className="text-sm font-medium">{allergies.join(', ')}</span>
          </div>
        </div>
      )}
      {chronicConditions.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          <HeartPulse className="mt-0.5 size-4 shrink-0" />
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-semibold tracking-wide uppercase">Chronic conditions</span>
            <span className="text-sm font-medium">{chronicConditions.join(', ')}</span>
          </div>
        </div>
      )}
    </div>
  )
}
