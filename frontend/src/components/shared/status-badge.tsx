import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// Covers every QueueTokenStatus and EncounterStatus value this app renders
// (backend/app/modules/checkin/models.py) under one consistent palette:
// amber = waiting to be seen, emerald = actively being seen, slate = done/
// neutral, rose = did-not-happen. Reused wherever a queue/encounter status
// is shown so the same status always reads the same color everywhere.
const STATUS_STYLES: Record<string, string> = {
  WAITING: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  CALLED: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  OPEN: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  IN_PROGRESS: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  IN_CONSULTATION: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  DONE: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20',
  COMPLETED: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20',
  SKIPPED: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20',
  NO_SHOW: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/20',
  CANCELLED: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/20',
  ACTIVE: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  INVITED: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  INACTIVE: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20',
}

const STATUS_LABELS: Record<string, string> = {
  WAITING: 'Waiting',
  CALLED: 'Called',
  OPEN: 'Open',
  IN_PROGRESS: 'In progress',
  IN_CONSULTATION: 'In consultation',
  DONE: 'Done',
  COMPLETED: 'Completed',
  SKIPPED: 'Skipped',
  NO_SHOW: 'No-show',
  CANCELLED: 'Cancelled',
  ACTIVE: 'Active',
  INVITED: 'Invited',
  INACTIVE: 'Inactive',
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn('border-transparent font-medium ring-1 ring-inset', STATUS_STYLES[status], className)}
    >
      {STATUS_LABELS[status] ?? status}
    </Badge>
  )
}
