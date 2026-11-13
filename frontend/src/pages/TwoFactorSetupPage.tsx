/**
 * Two-factor authentication enrollment (ADR-0093). For a login that requires enrollment, only this
 * page is shown whichever route is opened.
 *
 * Once confirmed, the token is refreshed. The server re-decides on refresh whether enrollment is
 * pending, so the permissions come back.
 */
import { ActionButton } from '../components/ActionButton'
import { AppMark } from '../components/AppMark'
import { TwoFactorControls } from '../components/TwoFactorControls'
import { usePendingAction } from '../hooks/usePendingAction'
import { useI18n } from '../i18n'
import { api } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function TwoFactorSetupPage() {
  const { t } = useI18n()
  const { refreshMe, logout } = useAuth()

  const onEnabled = async () => {
    await api.post('/api/auth/refresh')
    await refreshMe()
  }
  const [signOut, signingOut] = usePendingAction(logout)

  return (
    <div className="auth-page">
      <div className="card">
        <AppMark size={44} />
        <h1>{t('security.setupTitle')}</h1>
        <p className="hint">{t('security.setupHint')}</p>
        <TwoFactorControls onEnabled={onEnabled} />
        <div>
          <ActionButton type="button" pending={signingOut} onClick={signOut}>
            {t('security.setupSignOut')}
          </ActionButton>
        </div>
      </div>
    </div>
  )
}
