import { ClipboardList, LayoutDashboard, LogOut, Stethoscope, Users } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/features/auth/auth-context'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  permission?: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/patients', label: 'Patients', icon: Users, permission: 'patients.view_demographics' },
  { to: '/opd', label: 'OPD Queue', icon: ClipboardList, permission: 'consultation.manage' },
  { to: '/staff', label: 'Staff Directory', icon: Stethoscope, permission: 'staff.manage' },
]

export function AppShell() {
  const { user, hasPermission, logout } = useAuth()
  const visibleItems = NAV_ITEMS.filter((item) => !item.permission || hasPermission(item.permission))

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-4 py-4">
          <p className="text-sm font-semibold">Clinic ERP</p>
          <p className="truncate text-xs text-muted-foreground">
            {user?.first_name ?? user?.email ?? user?.phone}
          </p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-secondary text-secondary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )
              }
            >
              <item.icon className="size-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-2">
          <Button variant="ghost" className="w-full justify-start gap-2" onClick={() => void logout()}>
            <LogOut className="size-4" />
            Log out
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto bg-muted/20">
        <Outlet />
      </main>
    </div>
  )
}
