// Wraps the tokens needed to talk to the backend's tenant-slug-scoped auth
// endpoints (POST .../staff/refresh and .../staff/logout both require
// clinic_slug in the body, not just the bearer token — there's no session
// yet to derive tenant from at that point) — see backend/app/modules/auth/schemas.py.

const ACCESS_TOKEN_KEY = 'clinic_erp.access_token'
const REFRESH_TOKEN_KEY = 'clinic_erp.refresh_token'
const CLINIC_SLUG_KEY = 'clinic_erp.clinic_slug'

export interface StoredSession {
  accessToken: string
  refreshToken: string
  clinicSlug: string
}

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // localStorage unavailable (private mode, disabled storage) — the
    // session simply won't persist across reloads; nothing to recover here.
  }
}

function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // see safeSet
  }
}

export function getStoredSession(): StoredSession | null {
  const accessToken = safeGet(ACCESS_TOKEN_KEY)
  const refreshToken = safeGet(REFRESH_TOKEN_KEY)
  const clinicSlug = safeGet(CLINIC_SLUG_KEY)
  if (!accessToken || !refreshToken || !clinicSlug) return null
  return { accessToken, refreshToken, clinicSlug }
}

export function setStoredSession(session: StoredSession): void {
  safeSet(ACCESS_TOKEN_KEY, session.accessToken)
  safeSet(REFRESH_TOKEN_KEY, session.refreshToken)
  safeSet(CLINIC_SLUG_KEY, session.clinicSlug)
}

export function setStoredAccessToken(accessToken: string): void {
  safeSet(ACCESS_TOKEN_KEY, accessToken)
}

export function clearStoredSession(): void {
  safeRemove(ACCESS_TOKEN_KEY)
  safeRemove(REFRESH_TOKEN_KEY)
  safeRemove(CLINIC_SLUG_KEY)
}
