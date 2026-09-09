import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '@/features/auth/auth-context'

// `permission` accepts a single code, or an array meaning "any of" —
// mirrors the backend's own require_any_permission (app/api/deps.py),
// needed wherever two differently-scoped permissions both reach the same
// route (e.g. Billing: billing.manage for Owner/Receptionist, billing.view_own
// for Doctor/Patient — see backend/app/modules/billing/router.py).
//
// `redirectTo` is opt-in, not the default: most gated routes are simply
// absent from a role's nav (AppShell filters on the same permission), so
// landing here at all means a stale bookmark/URL — an inline explanation
// is the right response. /opd is the one route a role without
// consultation.manage can plausibly land on organically (e.g. a
// Receptionist reusing a doctor's browser session, or a bookmarked
// encounter URL), so it opts into a redirect instead of the banner.
export function RequirePermission({
  permission,
  redirectTo,
  children,
}: {
  permission: string | string[]
  redirectTo?: string
  children: ReactNode
}) {
  const { hasPermission } = useAuth()
  const permissions = Array.isArray(permission) ? permission : [permission]
  const allowed = permissions.some((p) => hasPermission(p))

  if (!allowed) {
    if (redirectTo) {
      return <Navigate to={redirectTo} replace />
    }
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-1 p-6 text-center">
        <p className="text-lg font-semibold">Not authorized</p>
        <p className="text-sm text-muted-foreground">
          Your role doesn't have the{' '}
          {permissions.map((p, i) => (
            <span key={p}>
              {i > 0 && ' or '}
              <code className="rounded bg-muted px-1 py-0.5">{p}</code>
            </span>
          ))}{' '}
          permission.
        </p>
      </div>
    )
  }

  return children
}
