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
  // Invoice statuses (backend/app/modules/billing/models.py::InvoiceStatus)
  DRAFT: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/10 dark:text-slate-400 dark:ring-slate-500/20',
  ISSUED: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  PARTIALLY_PAID: 'bg-blue-50 text-blue-700 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20',
  PAID: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  VOID: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/20',
  // Lab order statuses (backend/app/modules/lab/models.py::LabOrderStatus)
  // — COMPLETED/CANCELLED already defined above, reused as-is.
  ORDERED: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  SAMPLE_COLLECTED: 'bg-blue-50 text-blue-700 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-500/20',
  RESULTED: 'bg-violet-50 text-violet-700 ring-violet-600/20 dark:bg-violet-500/10 dark:text-violet-400 dark:ring-violet-500/20',
  // Lab result flags (backend/app/modules/lab/models.py::LabResultFlag)
  NORMAL: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  LOW: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  HIGH: 'bg-orange-50 text-orange-700 ring-orange-600/20 dark:bg-orange-500/10 dark:text-orange-400 dark:ring-orange-500/20',
  CRITICAL: 'bg-rose-100 text-rose-800 ring-rose-600/30 dark:bg-rose-500/20 dark:text-rose-300 dark:ring-rose-500/30',
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
  DRAFT: 'Draft',
  ISSUED: 'Issued',
  PARTIALLY_PAID: 'Partially paid',
  PAID: 'Paid',
  VOID: 'Void',
  ORDERED: 'Ordered',
  SAMPLE_COLLECTED: 'Sample collected',
  RESULTED: 'Resulted',
  NORMAL: 'Normal',
  LOW: 'Low',
  HIGH: 'High',
  CRITICAL: 'Critical',
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
