import { ClipboardList, LayoutDashboard, LogOut, Menu, Stethoscope, Users } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/features/auth/auth-context'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
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

function SidebarNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const { logout } = useAuth()

  return (
    <nav className="flex flex-1 flex-col gap-1 p-2">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          onClick={onNavigate}
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
      <div className="mt-auto border-t border-border pt-2">
        <Button variant="ghost" className="w-full justify-start gap-2" onClick={() => void logout()}>
          <LogOut className="size-4" />
          Log out
        </Button>
      </div>
    </nav>
  )
}

export function AppShell() {
  const { user, hasPermission } = useAuth()
  const visibleItems = NAV_ITEMS.filter((item) => !item.permission || hasPermission(item.permission))
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const identityLabel = user?.first_name ?? user?.email ?? user?.phone

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* Mobile/tablet top bar — the sidebar itself is hidden below md, this
          is the only chrome + entry point to navigation on a phone. */}
      <header className="flex items-center justify-between border-b border-border bg-card px-4 py-3 md:hidden">
        <div>
          <p className="text-sm font-semibold">Clinic ERP</p>
          <p className="truncate text-xs text-muted-foreground">{identityLabel}</p>
        </div>
        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetTrigger
            render={<Button variant="outline" size="icon" aria-label="Open navigation" />}
          >
            <Menu className="size-5" />
          </SheetTrigger>
          <SheetContent side="left" className="flex w-72 flex-col p-0">
            <SheetHeader className="border-b border-border">
              <SheetTitle>Clinic ERP</SheetTitle>
              <p className="truncate text-xs text-muted-foreground">{identityLabel}</p>
            </SheetHeader>
            <SidebarNav items={visibleItems} onNavigate={() => setMobileNavOpen(false)} />
          </SheetContent>
        </Sheet>
      </header>

      {/* Desktop/tablet-landscape sidebar */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-card md:flex">
        <div className="border-b border-border px-4 py-4">
          <p className="text-sm font-semibold">Clinic ERP</p>
          <p className="truncate text-xs text-muted-foreground">{identityLabel}</p>
        </div>
        <SidebarNav items={visibleItems} />
      </aside>

      <main className="flex-1 overflow-y-auto bg-muted/20">
        <Outlet />
      </main>
    </div>
  )
}
