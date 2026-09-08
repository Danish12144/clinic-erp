import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: number | undefined
  isLoading: boolean
  icon: LucideIcon
  accent: 'blue' | 'amber' | 'emerald' | 'violet'
}

const ACCENT_STYLES: Record<MetricCardProps['accent'], string> = {
  blue: 'bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400',
  amber: 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400',
  emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400',
  violet: 'bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400',
}

export function MetricCard({ label, value, isLoading, icon: Icon, accent }: MetricCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3.5">
        <div className={cn('flex size-11 shrink-0 items-center justify-center rounded-lg', ACCENT_STYLES[accent])}>
          <Icon className="size-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
          {isLoading ? (
            <Skeleton className="mt-1 h-7 w-12" />
          ) : (
            <span className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">
              {value ?? '—'}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
