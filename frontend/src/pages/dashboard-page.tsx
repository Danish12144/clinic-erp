import { Activity, ClipboardList, Stethoscope, UserPlus, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MetricCard } from '@/components/dashboard/metric-card'
import { NewPatientDialog } from '@/components/patients/new-patient-dialog'
import { StatusBadge } from '@/components/shared/status-badge'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/features/auth/auth-context'
import { useDashboardMetrics } from '@/features/dashboard/use-dashboard-metrics'
import { useRecentActivity } from '@/features/dashboard/use-recent-activity'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function DashboardPage() {
  const { user, hasPermission } = useAuth()
  const navigate = useNavigate()
  const metrics = useDashboardMetrics()
  const { rows: recentRows, isLoading: recentLoading, enabled: canViewActivity } = useRecentActivity()
  const [registerOpen, setRegisterOpen] = useState(false)

  const canRegister = hasPermission('patients.register')
  const canViewOpd = hasPermission('consultation.manage')
  const canViewStaff = hasPermission('staff.manage')

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
          Welcome back, {user?.first_name ?? 'there'}
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Here's what's happening at your clinic today.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {metrics.registeredPatients.visible && (
          <MetricCard
            label="Registered patients"
            value={metrics.registeredPatients.value}
            isLoading={metrics.registeredPatients.isLoading}
            icon={Users}
            accent="blue"
          />
        )}
        {metrics.todaysVisits.visible && (
          <MetricCard
            label="Today's OPD visits"
            value={metrics.todaysVisits.value}
            isLoading={metrics.todaysVisits.isLoading}
            icon={Activity}
            accent="violet"
          />
        )}
        {metrics.activeQueue.visible && (
          <MetricCard
            label="Active queue"
            value={metrics.activeQueue.value}
            isLoading={metrics.activeQueue.isLoading}
            icon={ClipboardList}
            accent="amber"
          />
        )}
        {metrics.doctorsOnDuty.visible && (
          <MetricCard
            label="Doctors on duty"
            value={metrics.doctorsOnDuty.value}
            isLoading={metrics.doctorsOnDuty.isLoading}
            icon={Stethoscope}
            accent="emerald"
          />
        )}
      </div>

      {(canRegister || canViewOpd || canViewStaff) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quick actions</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2.5">
            {canRegister && (
              <Button className="gap-1.5" onClick={() => setRegisterOpen(true)}>
                <UserPlus className="size-4" />
                Register walk-in
              </Button>
            )}
            {canViewOpd && (
              <Button variant="outline" className="gap-1.5" onClick={() => navigate('/opd')}>
                <Stethoscope className="size-4" />
                Write prescription
              </Button>
            )}
            {canViewOpd && (
              <Button variant="outline" className="gap-1.5" onClick={() => navigate('/opd')}>
                <ClipboardList className="size-4" />
                View queue
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {canViewActivity && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent activity</CardTitle>
            <CardDescription>The latest patients checked in across your clinic.</CardDescription>
          </CardHeader>
          <CardContent>
            {recentLoading ? (
              <div className="flex flex-col gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : recentRows.length === 0 ? (
              <EmptyState icon={Activity} title="No activity yet" description="Check-ins will show up here as they happen." />
            ) : (
              <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
                {recentRows.map(({ encounter, patient }) => (
                  <li key={encounter.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                        {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : 'Loading…'}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        Checked in at {formatTime(encounter.checked_in_at)}
                      </span>
                    </div>
                    <StatusBadge status={encounter.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      <NewPatientDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </div>
  )
}
