import { LayoutDashboard } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { getVisibleNavItems, type NavItem } from '@/components/layout/app-shell'

const ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/staff', label: 'Staff Directory', icon: LayoutDashboard, permission: 'staff.manage' },
  { to: '/billing', label: 'Billing', icon: LayoutDashboard, permission: ['billing.manage', 'billing.view_own'] },
]

describe('getVisibleNavItems', () => {
  it('always shows an item with no permission requirement', () => {
    const visible = getVisibleNavItems(ITEMS, () => false)
    expect(visible.map((i) => i.to)).toEqual(['/'])
  })

  it('shows a single-permission item only when the caller holds that exact code', () => {
    const visible = getVisibleNavItems(ITEMS, (code) => code === 'staff.manage')
    expect(visible.map((i) => i.to)).toContain('/staff')
    expect(visible.map((i) => i.to)).not.toContain('/billing')
  })

  it('treats an array-of-permissions item as "any of" — one matching code is enough', () => {
    const visible = getVisibleNavItems(ITEMS, (code) => code === 'billing.view_own')
    expect(visible.map((i) => i.to)).toContain('/billing')
  })

  it('shows every item when the caller holds every permission (e.g. Owner)', () => {
    const visible = getVisibleNavItems(ITEMS, () => true)
    expect(visible).toHaveLength(ITEMS.length)
  })
})
