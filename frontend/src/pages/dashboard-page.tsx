import { CheckCircle2, ClipboardList, Footprints, Ticket, UserCog, UserPlus, Users } from 'lucide-react'
import { useState } from 'react'
import { MetricCard } from '@/components/dashboard/metric-card'
import { InviteStaffDialog } from '@/components/staff/invite-staff-dialog'
import { IssueTokenDialog } from '@/components/patients/issue-token-dialog'
import { NewPatientDialog } from '@/components/patients/new-patient-dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { StatusBadge } from '@/components/shared/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/features/auth/auth-context'
import { useDashboardMetrics } from '@/features/dashboard/use-dashboard-metrics'
import { useLiveQueueSnapshot } from '@/features/dashboard/use-live-queue-snapshot'
import { useRecentRegistrations } from '@/features/dashboard/use-recent-registrations'

function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return new Date(iso).toLocaleDateString()
}

export function DashboardPage() {
  const { user, hasPermission } = useAuth()
  const metrics = useDashboardMetrics()
  const queueSnapshot = useLiveQueueSnapshot()
  const recentRegistrations = useRecentRegistrations()

  const [registerOpen, setRegisterOpen] = useState(false)
  const [issueTokenOpen, setIssueTokenOpen] = useState(false)
  const [addStaffOpen, setAddStaffOpen] = useState(false)

  const canRegister = hasPermission('patients.register')
  const canIssueToken = hasPermission('checkin.manage') && hasPermission('patients.view_demographics')
  const canAddStaff = hasPermission('staff.manage')

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">
          Welcome back, {user?.first_name ?? 'there'}
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">Here's what's happening at your clinic today.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        {metrics.todaysFootfall.visible && (
          <MetricCard
            label="Today's footfall"
            value={metrics.todaysFootfall.value}
            isLoading={metrics.todaysFootfall.isLoading}
            icon={Footprints}
            accent="blue"
          />
        )}
        {metrics.completedConsultations.visible && (
          <MetricCard
            label="Completed consultations"
            value={metrics.completedConsultations.value}
            isLoading={metrics.completedConsultations.isLoading}
            icon={CheckCircle2}
            accent="emerald"
          />
        )}
        {metrics.doctorsOnDuty.visible && (
          <MetricCard
            label="Active doctors on duty"
            value={metrics.doctorsOnDuty.value}
            isLoading={metrics.doctorsOnDuty.isLoading}
            icon={UserCog}
            accent="violet"
          />
        )}
        {metrics.registeredPatients.visible && (
          <MetricCard
            label="Total registered patients"
            value={metrics.registeredPatients.value}
            isLoading={metrics.registeredPatients.isLoading}
            icon={Users}
            accent="amber"
          />
        )}
      </div>

      {(canRegister || canIssueToken || canAddStaff) && (
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
            {canIssueToken && (
              <Button variant="outline" className="gap-1.5" onClick={() => setIssueTokenOpen(true)}>
                <Ticket className="size-4" />
                Issue token
              </Button>
            )}
            {canAddStaff && (
              <Button variant="outline" className="gap-1.5" onClick={() => setAddStaffOpen(true)}>
                <UserCog className="size-4" />
                Add staff
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {queueSnapshot.enabled && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Live queue</CardTitle>
              <CardDescription>Patients currently waiting or being seen, clinic-wide.</CardDescription>
            </CardHeader>
            <CardContent>
              {queueSnapshot.isLoading ? (
                <div className="flex flex-col gap-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : queueSnapshot.rows.length === 0 ? (
                <EmptyState icon={ClipboardList} title="Queue is empty" description="No patients are waiting right now." />
              ) : (
                <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
                  {queueSnapshot.rows.map(({ token, patient }) => (
                    <li key={token.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-sm font-medium text-slate-900 dark:text-slate-100">
                          #{token.token_number}
                        </span>
                        <span className="truncate text-sm text-slate-700 dark:text-slate-300">
                          {patient ? [patient.first_name, patient.last_name].filter(Boolean).join(' ') : <Skeleton className="h-4 w-24" />}
                        </span>
                      </div>
                      <StatusBadge status={token.status} />
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}

        {recentRegistrations.enabled && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent registrations</CardTitle>
              <CardDescription>The newest patients added to your clinic.</CardDescription>
            </CardHeader>
            <CardContent>
              {recentRegistrations.isLoading ? (
                <div className="flex flex-col gap-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : recentRegistrations.rows.length === 0 ? (
                <EmptyState icon={Users} title="No patients yet" description="Newly registered patients will show up here." />
              ) : (
                <ul className="flex flex-col divide-y divide-slate-100 dark:divide-slate-800">
                  {recentRegistrations.rows.map((patient) => (
                    <li key={patient.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                          {[patient.first_name, patient.last_name].filter(Boolean).join(' ')}
                        </span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">MRN {patient.mrn}</span>
                      </div>
                      <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
                        {formatRelativeTime(patient.created_at)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      <NewPatientDialog open={registerOpen} onOpenChange={setRegisterOpen} />
      <IssueTokenDialog open={issueTokenOpen} onOpenChange={setIssueTokenOpen} />
      <InviteStaffDialog open={addStaffOpen} onOpenChange={setAddStaffOpen} />
    </div>
  )
}
