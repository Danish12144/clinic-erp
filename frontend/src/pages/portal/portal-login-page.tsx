import { zodResolver } from '@hookform/resolvers/zod'
import { HeartPulse } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/auth-context'
import { getErrorMessage } from '@/lib/errors'

const phoneStepSchema = z.object({
  clinicSlug: z.string().min(1, 'Clinic slug is required'),
  phone: z.string().min(7, 'Enter a valid phone number'),
})
type PhoneStepValues = z.infer<typeof phoneStepSchema>

const codeStepSchema = z.object({
  code: z.string().min(4, 'Enter the code you received'),
})
type CodeStepValues = z.infer<typeof codeStepSchema>

export function PortalLoginPage() {
  const { status, user, requestOtp, loginWithOtp } = useAuth()
  const navigate = useNavigate()
  const [phoneStepData, setPhoneStepData] = useState<PhoneStepValues | null>(null)
  const [debugCode, setDebugCode] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)

  const phoneForm = useForm<PhoneStepValues>({ resolver: zodResolver(phoneStepSchema) })
  const codeForm = useForm<CodeStepValues>({ resolver: zodResolver(codeStepSchema) })

  // Already signed in — a PATIENT lands in the portal, staff go back to
  // the main app rather than seeing an OTP form that isn't for them.
  if (status === 'authenticated') {
    return <Navigate to={user?.role_code === 'PATIENT' ? '/portal' : '/'} replace />
  }

  async function onRequestOtp(values: PhoneStepValues) {
    setServerError(null)
    try {
      const result = await requestOtp(values.clinicSlug, values.phone)
      setPhoneStepData(values)
      setDebugCode(result.debugCode)
    } catch (error) {
      setServerError(getErrorMessage(error))
    }
  }

  async function onVerifyOtp(values: CodeStepValues) {
    if (!phoneStepData) return
    setServerError(null)
    try {
      await loginWithOtp(phoneStepData.clinicSlug, phoneStepData.phone, values.code)
      navigate('/portal', { replace: true })
    } catch {
      setServerError('That code is invalid or has expired — request a new one.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-900">
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
            <HeartPulse className="size-5" />
          </div>
          <span className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-50">Patient Portal</span>
        </div>

        {!phoneStepData ? (
          <Card className="w-full">
            <CardHeader>
              <CardTitle>Sign in</CardTitle>
              <CardDescription>Enter your clinic and phone number to receive a login code.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="flex flex-col gap-4" onSubmit={phoneForm.handleSubmit(onRequestOtp)} noValidate>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="portalClinicSlug">Clinic slug</Label>
                  <Input id="portalClinicSlug" autoComplete="organization" {...phoneForm.register('clinicSlug')} />
                  {phoneForm.formState.errors.clinicSlug && (
                    <p className="text-sm text-destructive">{phoneForm.formState.errors.clinicSlug.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="portalPhone">Phone number</Label>
                  <Input id="portalPhone" autoComplete="tel" {...phoneForm.register('phone')} />
                  {phoneForm.formState.errors.phone && <p className="text-sm text-destructive">{phoneForm.formState.errors.phone.message}</p>}
                </div>
                {serverError && <p className="text-sm text-destructive">{serverError}</p>}
                <Button type="submit" disabled={phoneForm.formState.isSubmitting} className="mt-2">
                  {phoneForm.formState.isSubmitting ? 'Sending…' : 'Send login code'}
                </Button>
              </form>
            </CardContent>
          </Card>
        ) : (
          <Card className="w-full">
            <CardHeader>
              <CardTitle>Enter your code</CardTitle>
              <CardDescription>We sent a login code to {phoneStepData.phone}.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="flex flex-col gap-4" onSubmit={codeForm.handleSubmit(onVerifyOtp)} noValidate>
                {debugCode && (
                  <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">
                    Dev only — no SMS provider configured yet. Your code: <span className="font-mono font-semibold">{debugCode}</span>
                  </p>
                )}
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="portalCode">Login code</Label>
                  <Input id="portalCode" inputMode="numeric" autoComplete="one-time-code" autoFocus {...codeForm.register('code')} />
                  {codeForm.formState.errors.code && <p className="text-sm text-destructive">{codeForm.formState.errors.code.message}</p>}
                </div>
                {serverError && <p className="text-sm text-destructive">{serverError}</p>}
                <Button type="submit" disabled={codeForm.formState.isSubmitting} className="mt-2">
                  {codeForm.formState.isSubmitting ? 'Verifying…' : 'Sign in'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setPhoneStepData(null)
                    setDebugCode(null)
                    setServerError(null)
                    codeForm.reset()
                  }}
                >
                  Use a different phone number
                </Button>
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
