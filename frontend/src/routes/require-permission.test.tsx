import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { RequirePermission } from '@/routes/require-permission'

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }))
vi.mock('@/features/auth/auth-context', () => ({ useAuth: useAuthMock }))

function mockPermissions(granted: string[]) {
  useAuthMock.mockReturnValue({ hasPermission: (code: string) => granted.includes(code) })
}

function renderGuarded(permission: string | string[], redirectTo?: string) {
  return render(
    <MemoryRouter initialEntries={['/guarded']}>
      <Routes>
        <Route
          path="/guarded"
          element={
            <RequirePermission permission={permission} redirectTo={redirectTo}>
              <p>Secret content</p>
            </RequirePermission>
          }
        />
        <Route path="/fallback" element={<p>Redirected here</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequirePermission', () => {
  it('renders children when the caller holds the required permission', () => {
    mockPermissions(['billing.manage'])
    renderGuarded('billing.manage')
    expect(screen.getByText('Secret content')).toBeInTheDocument()
  })

  it('shows an inline "Not authorized" message when the permission is missing and no redirectTo is set', () => {
    mockPermissions(['patients.view_demographics'])
    renderGuarded('billing.manage')
    expect(screen.queryByText('Secret content')).not.toBeInTheDocument()
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    expect(screen.getByText('billing.manage')).toBeInTheDocument()
  })

  it('treats an array of permissions as "any of" — passes if just one matches', () => {
    mockPermissions(['billing.view_own'])
    renderGuarded(['billing.manage', 'billing.view_own'])
    expect(screen.getByText('Secret content')).toBeInTheDocument()
  })

  it('fails an array permission check when none of the codes match', () => {
    mockPermissions(['patients.view_demographics'])
    renderGuarded(['billing.manage', 'billing.view_own'])
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
  })

  it('redirects instead of showing the banner when redirectTo is set and the permission is missing', () => {
    mockPermissions([])
    renderGuarded('consultation.manage', '/fallback')
    expect(screen.queryByText('Not authorized')).not.toBeInTheDocument()
    expect(screen.getByText('Redirected here')).toBeInTheDocument()
  })
})
