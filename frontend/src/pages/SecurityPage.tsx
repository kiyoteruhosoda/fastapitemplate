/**
 * Security (sign-in methods). A page under the profile (`/profile/security`).
 *
 * Password change, two-factor authentication and passkeys are one concern - "how to sign in" -
 * so they are separated from the profile and grouped on this page (ADR-0080 §4).
 */
import { Link } from 'react-router-dom'

import { FederatedIdentityControls } from '../components/FederatedIdentityControls'
import { PasskeyControls } from '../components/PasskeyControls'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { TwoFactorControls } from '../components/TwoFactorControls'
import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

export function SecurityPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  // No form for users without a password (ADR-0076 §6). Otherwise users who cannot enter a
  // "current password" would see input fields that can never succeed.
  const hasPassword = user?.has_password ?? true

  return (
    <div className="card">
      <h1>{t('security.title')}</h1>
      <p className="hint">{t('security.hint')}</p>

      <section className="settings-section">
        <h2>{t('changePassword.title')}</h2>
        {hasPassword ? (
          <PasswordChangeForm />
        ) : (
          <p className="hint">{t('changePassword.notSet')}</p>
        )}
      </section>

      <section className="settings-section">
        <h2>{t('security.twoFactor')}</h2>
        <TwoFactorControls />
      </section>

      <section className="settings-section">
        <h2>{t('security.passkeys')}</h2>
        <PasskeyControls />
      </section>

      <section className="settings-section">
        <h2>{t('security.federation')}</h2>
        <FederatedIdentityControls />
      </section>

      <div>
        <Link to="/profile">{t('security.backToProfile')}</Link>
      </div>
    </div>
  )
}
