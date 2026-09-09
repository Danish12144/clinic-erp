import { NavLink } from 'react-router-dom'
import { useAuth } from '@/features/auth/auth-context'
import { cn } from '@/lib/utils'

interface LabTab {
  to: string
  label: string
  permission: string | string[]
}

const TABS: LabTab[] = [
  { to: '/lab', label: 'Orders', permission: ['lab.order', 'lab.enter_results', 'lab.view_results'] },
  { to: '/lab/catalog', label: 'Catalog', permission: ['lab.manage_catalog', 'lab.order', 'lab.enter_results', 'lab.view_results'] },
]

export function LabTabs() {
  const { hasPermission } = useAuth()
  const visible = TABS.filter((tab) => (Array.isArray(tab.permission) ? tab.permission : [tab.permission]).some(hasPermission))

  if (visible.length <= 1) return null

  return (
    <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800">
      {visible.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end
          className={({ isActive }) =>
            cn(
              'border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'border-indigo-600 text-indigo-700 dark:text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-slate-100',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  )
}
