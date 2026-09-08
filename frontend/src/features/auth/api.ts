import { apiClient } from '@/lib/api-client'
import type {
  MeResponse,
  OtpRequestPayload,
  OtpVerifyPayload,
  StaffLoginRequest,
  TokenResponse,
} from '@/features/auth/types'

export async function staffLogin(payload: StaffLoginRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/staff/login', payload)
  return data
}

export async function requestPatientOtp(payload: OtpRequestPayload): Promise<{ message: string; debug_code: string | null }> {
  const { data } = await apiClient.post('/auth/patient/otp/request', payload)
  return data
}

export async function verifyPatientOtp(payload: OtpVerifyPayload): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/patient/otp/verify', payload)
  return data
}

export async function fetchMe(): Promise<MeResponse> {
  const { data } = await apiClient.get<MeResponse>('/auth/me')
  return data
}

export async function staffLogout(clinicSlug: string, refreshToken: string): Promise<void> {
  await apiClient.post('/auth/staff/logout', { clinic_slug: clinicSlug, refresh_token: refreshToken })
}
