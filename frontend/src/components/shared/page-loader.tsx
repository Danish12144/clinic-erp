import { Loader2 } from 'lucide-react'

// Suspense fallback shown while a route-level React.lazy() chunk loads —
// brief on a warm connection, so deliberately minimal rather than a full
// skeleton layout.
export function PageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 dark:bg-slate-900">
      <Loader2 className="size-6 animate-spin text-slate-400" />
    </div>
  )
}
