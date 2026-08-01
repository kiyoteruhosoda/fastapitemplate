import { Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { useI18n } from './i18n'
import { AdminDashboardPage } from './pages/AdminDashboardPage'
import { AuditLogsPage } from './pages/AuditLogsPage'
import { ConfigPage } from './pages/ConfigPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ItemsPage } from './pages/ItemsPage'
import { LoginPage } from './pages/LoginPage'
import { PermissionsPage } from './pages/PermissionsPage'
import { ProfilePage } from './pages/ProfilePage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { RolesPage } from './pages/RolesPage'
import { SecurityPage } from './pages/SecurityPage'
import { SystemLogsPage } from './pages/SystemLogsPage'
import { SystemStatusPage } from './pages/SystemStatusPage'
import { UsersPage } from './pages/UsersPage'
import { useAuth } from './store/AuthContext'

function RequireAuth() {
  const { user, loading } = useAuth()
  const { t } = useI18n()
  if (loading) return <p className="loading">{t('common.loading')}</p>
  if (!user) return <Navigate to="/login" replace />
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<AdminDashboardPage />} />
        <Route path="/items" element={<ItemsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/security" element={<SecurityPage />} />
        {/* パスワード変更はセキュリティの区画になり、セキュリティはプロフィールの
            下の画面へ移った（ADR-0020）。旧 URL のブックマークが行き止まりに
            ならないよう転送する。 */}
        <Route path="/change-password" element={<Navigate to="/profile/security" replace />} />
        <Route path="/security" element={<Navigate to="/profile/security" replace />} />
        <Route path="/admin/users" element={<UsersPage />} />
        <Route path="/admin/roles" element={<RolesPage />} />
        <Route path="/admin/permissions" element={<PermissionsPage />} />
        <Route path="/admin/config" element={<ConfigPage />} />
        <Route path="/admin/logs" element={<SystemLogsPage />} />
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
        <Route path="/admin/system-status" element={<SystemStatusPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
