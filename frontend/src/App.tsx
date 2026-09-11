import { QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { queryClient } from '@/app/query-client'
import { AppShell } from '@/components/layout/app-shell'
import { PortalShell } from '@/components/layout/portal-shell'
import { PageLoader } from '@/components/shared/page-loader'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/features/auth/auth-context'
import { RequireAuth } from '@/routes/require-auth'
import { RequirePatientAuth } from '@/routes/require-patient-auth'
import { RequirePermission } from '@/routes/require-permission'

// Route-level code-splitting: each page becomes its own chunk, fetched only
// when its route is actually visited, instead of all ~30 pages riding in
// the one ~740KB main bundle. AppShell/RequireAuth/RequirePermission stay
// eager (they're the layout shell every route renders inside of, not a
// route themselves) so navigating between already-visited routes doesn't
// re-suspend on shell chrome.
const LoginPage = lazy(() => import('@/pages/login-page').then((m) => ({ default: m.LoginPage })))
const DashboardPage = lazy(() => import('@/pages/dashboard-page').then((m) => ({ default: m.DashboardPage })))
const AppointmentsPage = lazy(() => import('@/pages/appointments-page').then((m) => ({ default: m.AppointmentsPage })))
const PatientsPage = lazy(() => import('@/pages/patients-page').then((m) => ({ default: m.PatientsPage })))
const StaffDirectoryPage = lazy(() => import('@/pages/staff-directory-page').then((m) => ({ default: m.StaffDirectoryPage })))
const OpdQueuePage = lazy(() => import('@/pages/opd-queue-page').then((m) => ({ default: m.OpdQueuePage })))
const OpdWorkspacePage = lazy(() => import('@/pages/opd-workspace-page').then((m) => ({ default: m.OpdWorkspacePage })))
const BillingPage = lazy(() => import('@/pages/billing-page').then((m) => ({ default: m.BillingPage })))
const InvoiceDetailPage = lazy(() => import('@/pages/invoice-detail-page').then((m) => ({ default: m.InvoiceDetailPage })))
const ReportsPage = lazy(() => import('@/pages/reports-page').then((m) => ({ default: m.ReportsPage })))
const InventoryPage = lazy(() => import('@/pages/inventory-page').then((m) => ({ default: m.InventoryPage })))
const ExpensesPage = lazy(() => import('@/pages/expenses-page').then((m) => ({ default: m.ExpensesPage })))
const PharmacyCatalogPage = lazy(() => import('@/pages/pharmacy-catalog-page').then((m) => ({ default: m.PharmacyCatalogPage })))
const PharmacyDispensePage = lazy(() => import('@/pages/pharmacy-dispense-page').then((m) => ({ default: m.PharmacyDispensePage })))
const PharmacySalesPage = lazy(() => import('@/pages/pharmacy-sales-page').then((m) => ({ default: m.PharmacySalesPage })))
const LabOrdersPage = lazy(() => import('@/pages/lab-orders-page').then((m) => ({ default: m.LabOrdersPage })))
const LabOrderDetailPage = lazy(() => import('@/pages/lab-order-detail-page').then((m) => ({ default: m.LabOrderDetailPage })))
const LabCatalogPage = lazy(() => import('@/pages/lab-catalog-page').then((m) => ({ default: m.LabCatalogPage })))
const LeadsPage = lazy(() => import('@/pages/leads-page').then((m) => ({ default: m.LeadsPage })))
const PortalLoginPage = lazy(() => import('@/pages/portal/portal-login-page').then((m) => ({ default: m.PortalLoginPage })))
const PortalHomePage = lazy(() => import('@/pages/portal/portal-home-page').then((m) => ({ default: m.PortalHomePage })))
const PortalAppointmentsPage = lazy(() =>
  import('@/pages/portal/portal-appointments-page').then((m) => ({ default: m.PortalAppointmentsPage })),
)
const PortalMedicalRecordsPage = lazy(() =>
  import('@/pages/portal/portal-medical-records-page').then((m) => ({ default: m.PortalMedicalRecordsPage })),
)
const PortalBillingPage = lazy(() => import('@/pages/portal/portal-billing-page').then((m) => ({ default: m.PortalBillingPage })))
const PortalLabResultsPage = lazy(() =>
  import('@/pages/portal/portal-lab-results-page').then((m) => ({ default: m.PortalLabResultsPage })),
)

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/portal/login" element={<PortalLoginPage />} />
              <Route
                element={
                  <RequirePatientAuth>
                    <PortalShell />
                  </RequirePatientAuth>
                }
              >
                <Route path="/portal" element={<PortalHomePage />} />
                <Route path="/portal/appointments" element={<PortalAppointmentsPage />} />
                <Route path="/portal/records" element={<PortalMedicalRecordsPage />} />
                <Route path="/portal/billing" element={<PortalBillingPage />} />
                <Route path="/portal/lab-results" element={<PortalLabResultsPage />} />
              </Route>
              <Route
                element={
                  <RequireAuth>
                    <AppShell />
                  </RequireAuth>
                }
              >
                <Route index element={<DashboardPage />} />
                <Route
                  path="/appointments"
                  element={
                    <RequirePermission permission="appointments.manage">
                      <AppointmentsPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/patients"
                  element={
                    <RequirePermission permission="patients.view_demographics">
                      <PatientsPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/staff"
                  element={
                    <RequirePermission permission="staff.manage">
                      <StaffDirectoryPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/opd"
                  element={
                    <RequirePermission permission="consultation.manage" redirectTo="/appointments">
                      <OpdQueuePage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/opd/:encounterId"
                  element={
                    <RequirePermission permission="consultation.manage" redirectTo="/appointments">
                      <OpdWorkspacePage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/billing"
                  element={
                    <RequirePermission permission={['billing.manage', 'billing.view_own']}>
                      <BillingPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/billing/:invoiceId"
                  element={
                    <RequirePermission permission={['billing.manage', 'billing.view_own']}>
                      <InvoiceDetailPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/reports"
                  element={
                    <RequirePermission permission={['dashboard.view', 'dashboard.view_own']}>
                      <ReportsPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/inventory"
                  element={
                    <RequirePermission permission={['inventory.manage', 'inventory.record_usage', 'inventory.view']}>
                      <InventoryPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/expenses"
                  element={
                    <RequirePermission permission={['expenses.manage', 'expenses.record']}>
                      <ExpensesPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/pharmacy"
                  element={
                    <RequirePermission permission="pharmacy.view_catalog">
                      <PharmacyCatalogPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/pharmacy/dispense"
                  element={
                    <RequirePermission permission="pharmacy.dispense">
                      <PharmacyDispensePage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/pharmacy/sales"
                  element={
                    <RequirePermission permission={['pharmacy.dispense', 'pharmacy.sell_otc']}>
                      <PharmacySalesPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/lab"
                  element={
                    <RequirePermission permission={['lab.order', 'lab.enter_results', 'lab.view_results']}>
                      <LabOrdersPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/lab/orders/:orderId"
                  element={
                    <RequirePermission permission={['lab.order', 'lab.enter_results', 'lab.view_results']}>
                      <LabOrderDetailPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/lab/catalog"
                  element={
                    <RequirePermission permission={['lab.manage_catalog', 'lab.order', 'lab.enter_results', 'lab.view_results']}>
                      <LabCatalogPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/leads"
                  element={
                    <RequirePermission permission="leads.manage">
                      <LeadsPage />
                    </RequirePermission>
                  }
                />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </AuthProvider>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  )
}
