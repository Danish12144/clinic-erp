import type { ReactNode } from 'react'
import { useAuth } from '@/features/auth/auth-context'

export function RequirePermission({ permission, children }: { permission: string; children: ReactNode }) {
  const { hasPermission } = useAuth()

  if (!hasPermission(permission)) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-1 p-6 text-center">
        <p className="text-lg font-semibold">Not authorized</p>
        <p className="text-sm text-muted-foreground">
          Your role doesn't have the <code className="rounded bg-muted px-1 py-0.5">{permission}</code> permission.
        </p>
      </div>
    )
  }

  return children
}
