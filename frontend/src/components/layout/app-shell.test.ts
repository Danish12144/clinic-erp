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

  it('is unaffected by a role with no explicit allowlist entry (e.g. OTHER_STAFF, or omitting the role entirely)', () => {
    const visible = getVisibleNavItems(ITEMS, () => true, 'OTHER_STAFF')
    expect(visible).toHaveLength(ITEMS.length)
  })

  it("hides a permission-granted item that isn't in the caller's strict role allowlist", () => {
    // NURSE holds every permission in this contrived fixture, but NURSE's
    // real-world allowlist (app-shell.tsx) only ever includes '/' and
    // '/opd' — neither /staff nor /billing exists in that allowlist, so
    // both stay hidden despite the permission check passing.
    const visible = getVisibleNavItems(ITEMS, () => true, 'NURSE')
    expect(visible.map((i) => i.to)).toEqual(['/'])
  })

  it("never shows an item outside the role allowlist even without the permission check failing", () => {
    const visible = getVisibleNavItems(ITEMS, (code) => code === 'billing.manage', 'DOCTOR')
    // DOCTOR's allowlist has no /billing entry, so it stays hidden despite
    // holding the permission that would otherwise show it.
    expect(visible.map((i) => i.to)).not.toContain('/billing')
  })

  it('lets OWNER (no allowlist entry) see everything the permission check allows', () => {
    const visible = getVisibleNavItems(ITEMS, () => true, 'OWNER')
    expect(visible).toHaveLength(ITEMS.length)
  })
})
