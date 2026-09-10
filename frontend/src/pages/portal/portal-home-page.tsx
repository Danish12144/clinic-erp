import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/features/auth/auth-context'
import { useMyPatient } from '@/features/patients/hooks'

export function PortalHomePage() {
  const { user } = useAuth()
  const { data: patient, isLoading } = useMyPatient()
  const displayName = [user?.first_name, user?.last_name].filter(Boolean).join(' ') || 'there'

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Welcome, {displayName}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Your personal health portal.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your details</CardTitle>
          <CardDescription>What the clinic has on file for you.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {isLoading ? (
            <>
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-32" />
            </>
          ) : patient ? (
            <>
              <p>
                <span className="text-slate-500 dark:text-slate-400">MRN: </span>
                {patient.mrn}
              </p>
              <p>
                <span className="text-slate-500 dark:text-slate-400">Phone: </span>
                {patient.phone || '—'}
              </p>
              <p>
                <span className="text-slate-500 dark:text-slate-400">Email: </span>
                {patient.email || '—'}
              </p>
            </>
          ) : (
            <p className="text-slate-500 dark:text-slate-400">Couldn't load your details right now.</p>
          )}
        </CardContent>
      </Card>

      <p className="text-sm text-slate-400 dark:text-slate-600">
        Appointments, medical records, prescriptions, billing, and lab results are coming to the portal soon.
      </p>
    </div>
  )
}
