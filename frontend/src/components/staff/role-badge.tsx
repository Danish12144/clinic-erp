import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

// All 8 system role codes (see backend/app/modules/auth — role_permissions
// seed). "Admin" isn't a real role in this system's 8-role model; OWNER is
// its closest equivalent, labeled accordingly rather than inventing a role
// the backend doesn't have.
export const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Owner',
  DOCTOR: 'Doctor',
  RECEPTIONIST: 'Receptionist',
  NURSE: 'Nurse',
  LAB_STAFF: 'Lab Staff',
  PHARMACY_STAFF: 'Pharmacy Staff',
  OTHER_STAFF: 'Other Staff',
  PATIENT: 'Patient',
}

const ROLE_COLORS: Record<string, string> = {
  OWNER: 'bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300',
  DOCTOR: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  RECEPTIONIST: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  NURSE: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  LAB_STAFF: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-500/15 dark:text-cyan-300',
  PHARMACY_STAFF: 'bg-pink-100 text-pink-800 dark:bg-pink-500/15 dark:text-pink-300',
  OTHER_STAFF: 'bg-slate-100 text-slate-800 dark:bg-slate-500/15 dark:text-slate-300',
  PATIENT: 'bg-gray-100 text-gray-800 dark:bg-gray-500/15 dark:text-gray-300',
}

export function RoleBadge({ roleCode, className }: { roleCode: string; className?: string }) {
  return (
    <Badge variant="outline" className={cn('border-transparent font-medium', ROLE_COLORS[roleCode], className)}>
      {ROLE_LABELS[roleCode] ?? roleCode}
    </Badge>
  )
}
