import type { ReactNode } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '@/features/auth/auth-context'

// Staff and patients share one AuthProvider/token-storage mechanism (see
// auth-context.tsx — it's already role-agnostic), so a staff member who's
// logged into the main app and wanders into /portal is "authenticated,"
// just not a PATIENT — that's a role mismatch, not an auth failure, and
// gets its own message rather than being bounced to /portal/login (which
// would just re-authenticate the same staff session right back here).
export function RequirePatientAuth({ children }: { children: ReactNode }) {
  const { status, user } = useAuth()

  if (status === 'loading') {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/portal/login" replace />
  }

  if (user?.role_code !== 'PATIENT') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-lg font-semibold">This area is for patients</p>
        <p className="text-sm text-muted-foreground">You're signed in as staff — head back to the main app instead.</p>
        <Link to="/" className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          Go to the staff dashboard
        </Link>
      </div>
    )
  }

  return children
}
