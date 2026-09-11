import { zodResolver } from '@hookform/resolvers/zod'
import { Stethoscope } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/features/auth/auth-context'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const loginSchema = z.object({
  clinicSlug: z.string().min(1, 'Clinic slug is required'),
  identifier: z.string().min(1, 'Email or phone is required'),
  password: z.string().min(1, 'Password is required'),
})

type LoginFormValues = z.infer<typeof loginSchema>

export function LoginPage() {
  const { status, loginWithPassword } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [serverError, setServerError] = useState<string | null>(null)

  // Captured exactly once, at mount — `location.state.from` (set by
  // RequireAuth's own redirect when it bounces an unauthenticated caller
  // here) is the correct "return them to the protected page they wanted"
  // target, but `history.state` survives a full reload of this same
  // /login URL (confirmed: real browser behavior, not a testing
  // artifact — F5, or navigating here again later in the same tab, both
  // reuse the entry rather than creating a fresh one). Left unhandled,
  // that means a much later, unrelated login (e.g. logging back in after
  // an explicit logout) could silently inherit a stale destination from
  // whatever page a *previous* session happened to get redirected from.
  // Capturing into a ref once, then scrubbing this entry's history state
  // via the effect below, means only the mount that actually received a
  // fresh redirect ever acts on it — a later reload of the same entry
  // finds nothing left to reuse.
  const redirectTarget = useRef(((location.state as { from?: Location } | null)?.from?.pathname ?? '/') as string)
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null })
    // Deliberately mount-only — location/navigate identity churns on every
    // render and would defeat the point of a once-only scrub.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  // The sole redirect mechanism, deliberately — a second, imperative
  // navigate('/') inside onSubmit used to race this render-time branch
  // (status flips to 'authenticated' mid-submit, which can re-render this
  // component and fire this Navigate before onSubmit's own call runs).
  // Single source of truth removes that race entirely.
  if (status === 'authenticated') {
    return <Navigate to={redirectTarget.current} replace />
  }

  async function onSubmit(values: LoginFormValues) {
    setServerError(null)
    try {
      await loginWithPassword(values.clinicSlug, values.identifier, values.password)
    } catch {
      setServerError('Invalid clinic, credentials, or password.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4 dark:bg-slate-900">
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
            <Stethoscope className="size-5" />
          </div>
          <span className="text-base font-semibold tracking-tight text-slate-900 dark:text-slate-50">Clinic ERP</span>
        </div>
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Clinic staff sign in</CardTitle>
            <CardDescription>Enter your clinic slug and credentials.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="clinicSlug">Clinic slug</Label>
                <Input id="clinicSlug" autoComplete="organization" {...register('clinicSlug')} />
                {errors.clinicSlug && <p className="text-sm text-destructive">{errors.clinicSlug.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="identifier">Email or phone</Label>
                <Input id="identifier" autoComplete="username" {...register('identifier')} />
                {errors.identifier && <p className="text-sm text-destructive">{errors.identifier.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
                {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
              </div>
              {serverError && <p className="text-sm text-destructive">{serverError}</p>}
              <Button type="submit" disabled={isSubmitting} className="mt-2">
                {isSubmitting ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Are you a patient?{' '}
          <Link to="/portal/login" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
            Go to Patient Portal
          </Link>
        </p>
      </div>
    </div>
  )
}
