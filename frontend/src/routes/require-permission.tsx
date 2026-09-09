import type { ReactNode } from 'react'
import { useAuth } from '@/features/auth/auth-context'

// `permission` accepts a single code, or an array meaning "any of" —
// mirrors the backend's own require_any_permission (app/api/deps.py),
// needed wherever two differently-scoped permissions both reach the same
// route (e.g. Billing: billing.manage for Owner/Receptionist, billing.view_own
// for Doctor/Patient — see backend/app/modules/billing/router.py).
export function RequirePermission({ permission, children }: { permission: string | string[]; children: ReactNode }) {
  const { hasPermission } = useAuth()
  const permissions = Array.isArray(permission) ? permission : [permission]
  const allowed = permissions.some((p) => hasPermission(p))

  if (!allowed) {
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
