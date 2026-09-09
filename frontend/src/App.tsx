import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { queryClient } from '@/app/query-client'
import { AppShell } from '@/components/layout/app-shell'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/features/auth/auth-context'
import { BillingPage } from '@/pages/billing-page'
import { DashboardPage } from '@/pages/dashboard-page'
import { InvoiceDetailPage } from '@/pages/invoice-detail-page'
import { LoginPage } from '@/pages/login-page'
import { OpdQueuePage } from '@/pages/opd-queue-page'
import { OpdWorkspacePage } from '@/pages/opd-workspace-page'
import { PatientsPage } from '@/pages/patients-page'
import { StaffDirectoryPage } from '@/pages/staff-directory-page'
import { RequireAuth } from '@/routes/require-auth'
import { RequirePermission } from '@/routes/require-permission'

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <RequireAuth>
                  <AppShell />
                </RequireAuth>
              }
            >
              <Route index element={<DashboardPage />} />
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
                  <RequirePermission permission="consultation.manage">
                    <OpdQueuePage />
                  </RequirePermission>
                }
              />
              <Route
                path="/opd/:encounterId"
                element={
                  <RequirePermission permission="consultation.manage">
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
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  )
}
