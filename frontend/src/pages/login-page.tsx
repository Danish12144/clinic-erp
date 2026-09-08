import { zodResolver } from '@hookform/resolvers/zod'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
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
  const navigate = useNavigate()
  const location = useLocation()
  const [serverError, setServerError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) })

  if (status === 'authenticated') {
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/'
    return <Navigate to={from} replace />
  }

  async function onSubmit(values: LoginFormValues) {
    setServerError(null)
    try {
      await loginWithPassword(values.clinicSlug, values.identifier, values.password)
      navigate('/', { replace: true })
    } catch {
      setServerError('Invalid clinic, credentials, or password.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
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
    </div>
  )
}
