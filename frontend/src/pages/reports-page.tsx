import { BarChart3, Download, IndianRupee, Receipt, RefreshCcw, Wallet } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { EmptyState } from '@/components/shared/empty-state'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useAuth } from '@/features/auth/auth-context'
import { useBranches } from '@/features/branches/hooks'
import { useBookableDoctors } from '@/features/doctors/hooks'
import { exportFinancialReportCsv } from '@/features/reports/api'
import { useBillingSummary, useFinancialReport } from '@/features/reports/hooks'
import { REPORT_PERIODS, type ReportPeriod } from '@/features/reports/types'
import { downloadBlob } from '@/lib/download'
import { getErrorMessage } from '@/lib/errors'

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const PERIOD_LABELS: Record<ReportPeriod, string> = {
  today: 'Today',
  '7_days': 'Last 7 days',
  '30_days': 'Last 30 days',
  all_time: 'All time',
  custom: 'Custom range',
}

function KpiCard({ label, value, isLoading, icon: Icon }: { label: string; value: string; isLoading: boolean; icon: typeof BarChart3 }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3.5">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
          <Icon className="size-5" />
        </div>
        <div className="flex flex-col">
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
          {isLoading ? <Skeleton className="mt-1 h-7 w-20" /> : (
            <span className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">{value}</span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export function ReportsPage() {
  const { hasPermission } = useAuth()
  const isOwnerScope = hasPermission('dashboard.view')

  const { data: branches } = useBranches()
  const { doctors } = useBookableDoctors()

  const [period, setPeriod] = useState<ReportPeriod>('30_days')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [branchId, setBranchId] = useState('')
  const [doctorId, setDoctorId] = useState('')
  const [exporting, setExporting] = useState(false)

  const queryParams = {
    period,
    dateFrom: period === 'custom' && dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined,
    dateTo: period === 'custom' && dateTo ? new Date(`${dateTo}T23:59:59.999`).toISOString() : undefined,
    branchId: branchId || undefined,
    doctorId: isOwnerScope && doctorId ? doctorId : undefined,
  }

  const { data: summary, isLoading: summaryLoading } = useBillingSummary(queryParams)
  const { data: report, isLoading: reportLoading } = useFinancialReport(queryParams)

  const customRangeIncomplete = period === 'custom' && (!dateFrom || !dateTo)

  async function onExportCsv() {
    setExporting(true)
    try {
      const blob = await exportFinancialReportCsv(queryParams)
      downloadBlob(blob, 'financial-report.csv')
    } catch (error) {
      toast.error('Could not export report', { description: getErrorMessage(error) })
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-50">Reports & Analytics</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {isOwnerScope ? 'Revenue and collections across your clinic.' : 'Revenue and collections for your own consultations.'}
          </p>
        </div>
        <Button variant="outline" className="gap-1.5" onClick={onExportCsv} disabled={exporting || customRangeIncomplete}>
          <Download className="size-4" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label>Period</Label>
          <Select value={period} onValueChange={(value) => value && setPeriod(value as ReportPeriod)}>
            <SelectTrigger className="w-full sm:w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REPORT_PERIODS.map((p) => (
                <SelectItem key={p} value={p}>
                  {PERIOD_LABELS[p]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {period === 'custom' && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reportDateFrom">From</Label>
              <Input id="reportDateFrom" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full sm:w-40" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reportDateTo">To</Label>
              <Input id="reportDateTo" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full sm:w-40" />
            </div>
          </>
        )}

        {branches && branches.length > 1 && (
          <div className="flex flex-col gap-1.5">
            <Label>Branch</Label>
            <Select value={branchId || 'ALL'} onValueChange={(value) => setBranchId(value === 'ALL' ? '' : (value ?? ''))}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="All branches" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All branches</SelectItem>
                {branches.map((branch) => (
                  <SelectItem key={branch.id} value={branch.id}>
                    {branch.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {isOwnerScope && doctors.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <Label>Doctor</Label>
            <Select value={doctorId || 'ALL'} onValueChange={(value) => setDoctorId(value === 'ALL' ? '' : (value ?? ''))}>
              <SelectTrigger className="w-full sm:w-48">
                <SelectValue placeholder="All doctors" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All doctors</SelectItem>
                {doctors.map((doc) => (
                  <SelectItem key={doc.userId} value={doc.userId}>
                    {doc.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {customRangeIncomplete ? (
        <EmptyState icon={BarChart3} title="Pick a date range" description="Select both a from and to date to run this report." />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <KpiCard label="Total billed" value={report ? formatMoney(report.total_billed) : '—'} isLoading={reportLoading} icon={Receipt} />
            <KpiCard label="Total collected" value={summary ? formatMoney(summary.total_collected) : '—'} isLoading={summaryLoading} icon={IndianRupee} />
            <KpiCard label="Total refunded" value={summary ? formatMoney(summary.total_refunds) : '—'} isLoading={summaryLoading} icon={RefreshCcw} />
            <KpiCard label="Net collected" value={report ? formatMoney(report.net_collected) : '—'} isLoading={reportLoading} icon={Wallet} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Revenue by service type</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Service type</TableHead>
                      <TableHead className="text-right">Billed</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reportLoading &&
                      Array.from({ length: 3 }).map((_, i) => (
                        <TableRow key={i}>
                          <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                        </TableRow>
                      ))}
                    {!reportLoading && (report?.by_service_type.length ?? 0) === 0 && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={2}>
                          <EmptyState icon={Receipt} title="No billed revenue" description="No invoices were billed in this period." />
                        </TableCell>
                      </TableRow>
                    )}
                    {!reportLoading &&
                      report?.by_service_type.map((row) => (
                        <TableRow key={row.source_type}>
                          <TableCell className="font-medium text-slate-900 dark:text-slate-100">{row.source_type}</TableCell>
                          <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(row.total_billed)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">By payment mode</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Method</TableHead>
                      <TableHead className="text-right">Collected</TableHead>
                      <TableHead className="text-right">Refunded</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reportLoading &&
                      Array.from({ length: 3 }).map((_, i) => (
                        <TableRow key={i}>
                          <TableCell><Skeleton className="h-4 w-20" /></TableCell>
                          <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                          <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                        </TableRow>
                      ))}
                    {!reportLoading && (report?.by_payment_mode.length ?? 0) === 0 && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell colSpan={3}>
                          <EmptyState icon={Wallet} title="No payments recorded" description="No payments were collected in this period." />
                        </TableCell>
                      </TableRow>
                    )}
                    {!reportLoading &&
                      report?.by_payment_mode.map((row) => (
                        <TableRow key={row.method}>
                          <TableCell className="font-medium text-slate-900 dark:text-slate-100">{row.method}</TableCell>
                          <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(row.collected)}</TableCell>
                          <TableCell className="text-right text-slate-700 dark:text-slate-300">{formatMoney(row.refunded)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <p className="text-xs text-slate-400 dark:text-slate-500">
            {summary?.total_bills_raised ?? 0} bill{summary?.total_bills_raised === 1 ? '' : 's'} raised · {summary?.payment_modes_tracked ?? 0} payment mode
            {summary?.payment_modes_tracked === 1 ? '' : 's'} used in this period.
          </p>
        </>
      )}
    </div>
  )
}
