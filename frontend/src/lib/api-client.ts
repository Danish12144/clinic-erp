import axios, { type AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { emitSessionExpired } from '@/lib/auth-events'
import { clearStoredSession, getStoredSession, setStoredSession } from '@/lib/token-storage'
import type { AccessTokenOnlyResponse } from '@/features/auth/types'

const API_BASE_URL = `${import.meta.env.VITE_API_BASE_URL}/api/v1`

// Requests to these paths never get a bearer token attached (there isn't one
// yet) and never trigger the 401 -> refresh -> retry dance below — a 401 from
// one of these *is* the real answer (bad password, expired OTP, ...), not a
// stale-access-token situation.
const AUTH_EXEMPT_PATHS = [
  '/auth/staff/login',
  '/auth/staff/refresh',
  '/auth/patient/otp/request',
  '/auth/patient/otp/verify',
  '/auth/accept-invite',
]

function isAuthExempt(url: string | undefined): boolean {
  if (!url) return false
  return AUTH_EXEMPT_PATHS.some((path) => url.includes(path))
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
})

// A bare instance with no interceptors, used only to call the refresh
// endpoint itself — routing that call back through `apiClient` would recurse
// into this same 401 handler.
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (!isAuthExempt(config.url)) {
    const session = getStoredSession()
    if (session) {
      config.headers.set('Authorization', `Bearer ${session.accessToken}`)
    }
  }
  return config
})

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const session = getStoredSession()
  if (!session) throw new Error('No session to refresh')

  const { data } = await refreshClient.post<AccessTokenOnlyResponse>('/auth/staff/refresh', {
    clinic_slug: session.clinicSlug,
    refresh_token: session.refreshToken,
  })
  setStoredSession({
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    clinicSlug: session.clinicSlug,
  })
  return data.access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequestConfig | undefined

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retried ||
      isAuthExempt(originalRequest.url)
    ) {
      return Promise.reject(error)
    }

    if (!getStoredSession()) {
      // Never had a session (or it was already cleared) — nothing to
      // refresh; this is a real "you're not logged in," not a stale token.
      return Promise.reject(error)
    }

    originalRequest._retried = true

    try {
      // Coalesce concurrent 401s onto a single in-flight refresh call rather
      // than firing one refresh request per failed request.
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null
      })
      const newAccessToken = await refreshPromise
      originalRequest.headers.set('Authorization', `Bearer ${newAccessToken}`)
      return apiClient(originalRequest)
    } catch (refreshError) {
      clearStoredSession()
      emitSessionExpired()
      return Promise.reject(refreshError)
    }
  },
)

export type { AxiosRequestConfig }
