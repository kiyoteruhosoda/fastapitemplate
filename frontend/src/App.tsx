import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { useI18n } from './i18n'
import { AdminDashboardPage } from './pages/AdminDashboardPage'
import { AppReturnPage } from './pages/AppReturnPage'
import { AuditLogsPage } from './pages/AuditLogsPage'
import { ConfigPage } from './pages/ConfigPage'
import { ContentSettingsPage } from './pages/ContentSettingsPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { GroupsPage } from './pages/GroupsPage'
import { ItemsPage } from './pages/ItemsPage'
import { LoginPage } from './pages/LoginPage'
import { NotesPage } from './pages/NotesPage'
import { NotificationsAdminPage } from './pages/NotificationsAdminPage'
import { SsoCallbackPage } from './pages/SsoCallbackPage'
import { PermissionsPage } from './pages/PermissionsPage'
import { ProfilePage } from './pages/ProfilePage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'
import { RolesPage } from './pages/RolesPage'
import { SecurityPage } from './pages/SecurityPage'
import { SystemAdministratorsPage } from './pages/SystemAdministratorsPage'
import { SystemLogsPage } from './pages/SystemLogsPage'
import { SystemStatusPage } from './pages/SystemStatusPage'
import { TenantsPage } from './pages/TenantsPage'
import { TwoFactorSetupPage } from './pages/TwoFactorSetupPage'
import { UsersPage } from './pages/UsersPage'
import { signInPathFor } from './services/returnTo'
import { useAuth } from './store/AuthContext'

function RequireAuth() {
  const { user, loading, unreachable } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  if (loading) return <p className="loading">{t('common.loading')}</p>
  // Don't send to the sign-in screen when merely unreachable (e.g. during a release; it recovers automatically once connected)
  if (!user && unreachable)
    return (
      <p className="loading">
        <span className="spinner" aria-hidden="true" /> {t('common.unreachable')}
      </p>
    )
  // Carry the screen being opened (ADR-0077 §8). Without it, sign-in lands on the landing page.
  if (!user) return <Navigate to={signInPathFor(location)} replace />
  // Keep the route. Once registration is done, the screen being opened shows as is (ADR-0093)
  if (user.two_factor_setup_required) return <TwoFactorSetupPage />
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
      {/* Per-tenant entrance (ADR-0079 §4) */}
      <Route path="/t/:tenant/login" element={<LoginPage />} />
      <Route path="/t/:tenant/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/login/sso" element={<SsoCallbackPage />} />
      <Route path="/app/oauth2redirect" element={<AppReturnPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<AdminDashboardPage />} />
        <Route path="/items" element={<ItemsPage />} />
        <Route path="/notes" element={<NotesPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/security" element={<SecurityPage />} />
        {/* Password change became a section of Security, and Security moved under the
            Profile screen (ADR-0080 §4). Redirect so bookmarks of the old URL don't
            dead-end. */}
        <Route path="/change-password" element={<Navigate to="/profile/security" replace />} />
        <Route path="/security" element={<Navigate to="/profile/security" replace />} />
        <Route path="/admin/users" element={<UsersPage />} />
        <Route path="/admin/roles" element={<RolesPage />} />
        <Route path="/admin/permissions" element={<PermissionsPage />} />
        <Route path="/admin/groups" element={<GroupsPage />} />
        <Route path="/admin/notifications" element={<NotificationsAdminPage />} />
        <Route path="/admin/content-settings" element={<ContentSettingsPage />} />
        <Route path="/admin/config" element={<ConfigPage />} />
        <Route path="/admin/logs" element={<SystemLogsPage />} />
        <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
        <Route path="/admin/system-status" element={<SystemStatusPage />} />
        <Route path="/system/tenants" element={<TenantsPage />} />
        <Route path="/system/administrators" element={<SystemAdministratorsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
