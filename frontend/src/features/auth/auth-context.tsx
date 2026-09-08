import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchMe, requestPatientOtp, staffLogin, staffLogout, verifyPatientOtp } from '@/features/auth/api'
import type { UserSummary } from '@/features/auth/types'
import { onSessionExpired } from '@/lib/auth-events'
import { clearStoredSession, getStoredSession, setStoredSession } from '@/lib/token-storage'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  status: AuthStatus
  user: UserSummary | null
  permissions: string[]
  hasPermission: (permissionCode: string) => boolean
  loginWithPassword: (clinicSlug: string, identifier: string, password: string) => Promise<void>
  requestOtp: (clinicSlug: string, phone: string) => Promise<{ message: string; debugCode: string | null }>
  loginWithOtp: (clinicSlug: string, phone: string, code: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  // No stored session at all means there's nothing to hydrate — start
  // "unauthenticated" straight away instead of a "loading" state the effect
  // below would just immediately flip back, which is what an unconditional
  // setState-in-effect would otherwise do on every mount.
  const [status, setStatus] = useState<AuthStatus>(() => (getStoredSession() ? 'loading' : 'unauthenticated'))
  const [user, setUser] = useState<UserSummary | null>(null)
  const [permissions, setPermissions] = useState<string[]>([])

  const clearSession = useCallback(() => {
    clearStoredSession()
    setUser(null)
    setPermissions([])
    setStatus('unauthenticated')
  }, [])

  const hydrateFromMe = useCallback(async () => {
    const me = await fetchMe()
    setUser(me.user)
    setPermissions(me.permissions)
    setStatus('authenticated')
  }, [])

  // On first mount, a stored session's access token may already be expired —
  // fetchMe() going through apiClient still recovers via the 401 -> refresh
  // -> retry interceptor, so this isn't a redundant refresh-on-load, it's
  // the one place that turns "tokens on disk" into "confirmed live session."
  // hydrateFromMe/clearSession are both stable (empty-dep useCallback), so
  // this genuinely only ever runs once, against whatever session existed at
  // mount — loginWithPassword/loginWithOtp call hydrateFromMe themselves
  // after establishing a new session.
  useEffect(() => {
    if (!getStoredSession()) return
    hydrateFromMe().catch(() => clearSession())
  }, [hydrateFromMe, clearSession])

  useEffect(() => onSessionExpired(clearSession), [clearSession])

  const loginWithPassword = useCallback(
    async (clinicSlug: string, identifier: string, password: string) => {
      const token = await staffLogin({ clinic_slug: clinicSlug, identifier, password })
      setStoredSession({ accessToken: token.access_token, refreshToken: token.refresh_token, clinicSlug })
      await hydrateFromMe()
    },
    [hydrateFromMe],
  )

  const requestOtp = useCallback(async (clinicSlug: string, phone: string) => {
    const result = await requestPatientOtp({ clinic_slug: clinicSlug, phone })
    return { message: result.message, debugCode: result.debug_code }
  }, [])

  const loginWithOtp = useCallback(
    async (clinicSlug: string, phone: string, code: string) => {
      const token = await verifyPatientOtp({ clinic_slug: clinicSlug, phone, code })
      setStoredSession({ accessToken: token.access_token, refreshToken: token.refresh_token, clinicSlug })
      await hydrateFromMe()
    },
    [hydrateFromMe],
  )

  const logout = useCallback(async () => {
    const session = getStoredSession()
    if (session) {
      try {
        await staffLogout(session.clinicSlug, session.refreshToken)
      } catch {
        // Best-effort — the refresh token gets orphaned server-side at worst
        // (it'll simply expire on its own); the local session must clear
        // either way so the UI doesn't get stuck "logged in."
      }
    }
    clearSession()
  }, [clearSession])

  const hasPermission = useCallback((permissionCode: string) => permissions.includes(permissionCode), [permissions])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, permissions, hasPermission, loginWithPassword, requestOtp, loginWithOtp, logout }),
    [status, user, permissions, hasPermission, loginWithPassword, requestOtp, loginWithOtp, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
