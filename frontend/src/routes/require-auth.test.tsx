import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { RequireAuth } from '@/routes/require-auth'

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }))
vi.mock('@/features/auth/auth-context', () => ({ useAuth: useAuthMock }))

function renderGuarded(status: 'loading' | 'authenticated' | 'unauthenticated') {
  useAuthMock.mockReturnValue({ status })
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <p>Dashboard content</p>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<p>Login page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireAuth', () => {
  it('shows a loading indicator while the session is being resolved', () => {
    renderGuarded('loading')
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('redirects to /login when unauthenticated', () => {
    renderGuarded('unauthenticated')
    expect(screen.getByText('Login page')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard content')).not.toBeInTheDocument()
  })

  it('renders children when authenticated', () => {
    renderGuarded('authenticated')
    expect(screen.getByText('Dashboard content')).toBeInTheDocument()
  })
})
