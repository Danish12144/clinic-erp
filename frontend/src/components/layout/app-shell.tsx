import { ClipboardList, FlaskConical, LayoutDashboard, LogOut, Menu, Pill, Receipt, Stethoscope, Users } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { RoleBadge } from '@/components/staff/role-badge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { useAuth } from '@/features/auth/auth-context'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  // Any one of these permissions is enough to show the item — mirrors
  // RequirePermission's "any of" semantics (backend's require_any_permission).
  permission?: string | string[]
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/patients', label: 'Patients', icon: Users, permission: 'patients.view_demographics' },
  { to: '/opd', label: 'OPD Queue', icon: ClipboardList, permission: 'consultation.manage' },
  { to: '/billing', label: 'Billing', icon: Receipt, permission: ['billing.manage', 'billing.view_own'] },
  { to: '/pharmacy', label: 'Pharmacy', icon: Pill, permission: 'pharmacy.view_catalog' },
  { to: '/lab', label: 'Lab', icon: FlaskConical, permission: ['lab.order', 'lab.enter_results', 'lab.manage_catalog'] },
  { to: '/staff', label: 'Staff Directory', icon: Stethoscope, permission: 'staff.manage' },
]

function BrandMark() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
        <Stethoscope className="size-4.5" />
      </div>
      <span className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-50">Clinic ERP</span>
    </div>
  )
}

function initialsFor(label: string | null | undefined): string {
  if (!label) return '?'
  const parts = label.trim().split(/\s+/)
  const initials = parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : label.slice(0, 2)
  return initials.toUpperCase()
}

function UserFooter() {
  const { user, logout } = useAuth()
  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email || user?.phone || 'Unknown user'

  return (
    <div className="flex items-center gap-2.5 border-t border-slate-200 p-3 dark:border-slate-800">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400">
        {initialsFor(displayName)}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-50">{displayName}</p>
        {user && <RoleBadge roleCode={user.role_code} className="w-fit text-[0.65rem]" />}
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="Log out"
        className="shrink-0 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
        onClick={() => void logout()}
      >
        <LogOut className="size-4" />
      </Button>
    </div>
  )
}

function SidebarNav({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-1 flex-col gap-0.5 p-3">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-400'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100',
            )
          }
        >
          <item.icon className="size-4" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { hasPermission } = useAuth()
  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.permission || (Array.isArray(item.permission) ? item.permission : [item.permission]).some(hasPermission),
  )
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      {/* Mobile/tablet top bar — the sidebar itself is hidden below md, this
          is the only chrome + entry point to navigation on a phone. */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden dark:border-slate-800 dark:bg-slate-950">
        <BrandMark />
        <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
          <SheetTrigger render={<Button variant="outline" size="icon" aria-label="Open navigation" />}>
            <Menu className="size-5" />
          </SheetTrigger>
          <SheetContent side="left" className="flex w-72 flex-col p-0">
            <SheetHeader className="border-b border-slate-200 dark:border-slate-800">
              <BrandMark />
              <SheetTitle className="sr-only">Navigation</SheetTitle>
            </SheetHeader>
            <SidebarNav items={visibleItems} onNavigate={() => setMobileNavOpen(false)} />
            <UserFooter />
          </SheetContent>
        </Sheet>
      </header>

      {/* Desktop/tablet-landscape sidebar */}
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex dark:border-slate-800 dark:bg-slate-950">
        <div className="border-b border-slate-200 px-4 py-4 dark:border-slate-800">
          <BrandMark />
        </div>
        <SidebarNav items={visibleItems} />
        <UserFooter />
      </aside>

      <main className="flex-1 overflow-y-auto bg-slate-50 dark:bg-slate-900">
        <Outlet />
      </main>
    </div>
  )
}
