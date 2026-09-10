import { HeartPulse, LogOut } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/auth-context'
import { cn } from '@/lib/utils'

// Deliberately only lists screens that actually exist — add an entry here
// as each portal screen ships (Appointments, Medical Records,
// Prescriptions, Billing, Lab Results), not ahead of it; a nav link to a
// route that 404s is worse than a short nav.
const PORTAL_NAV_ITEMS = [{ to: '/portal', label: 'Home' }]

export function PortalShell() {
  const { user, logout } = useAuth()
  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'Patient'

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 dark:bg-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sm:px-6 dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
            <HeartPulse className="size-4.5" />
          </div>
          <span className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-50">Patient Portal</span>
        </div>
        <nav className="hidden items-center gap-1 sm:flex">
          {PORTAL_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) =>
                cn(
                  'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <span className="hidden text-sm text-slate-500 sm:inline dark:text-slate-400">{displayName}</span>
          <Button variant="ghost" size="icon-sm" aria-label="Log out" onClick={() => void logout()}>
            <LogOut className="size-4" />
          </Button>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}
