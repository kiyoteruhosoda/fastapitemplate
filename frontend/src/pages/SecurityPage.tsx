/**
 * セキュリティ（サインインの手段）。プロフィールの下の画面（`/profile/security`）。
 *
 * パスワードの変更・二要素認証・パスキーは「どうやってサインインするか」という
 * 1 つの関心なので、プロフィールから分けてこの画面にまとめる（ADR-0020）。
 */
import { Link } from 'react-router-dom'

import { PasskeyControls } from '../components/PasskeyControls'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { TwoFactorControls } from '../components/TwoFactorControls'
import { useI18n } from '../i18n'

export function SecurityPage() {
  const { t } = useI18n()

  return (
    <div className="card">
      <h1>{t('security.title')}</h1>
      <p className="hint">{t('security.hint')}</p>

      <section className="settings-section">
        <h2>{t('changePassword.title')}</h2>
        <PasswordChangeForm />
      </section>

      <section className="settings-section">
        <h2>{t('security.twoFactor')}</h2>
        <TwoFactorControls />
      </section>

      <section className="settings-section">
        <h2>{t('security.passkeys')}</h2>
        <PasskeyControls />
      </section>

      <div>
        <Link to="/profile">{t('security.backToProfile')}</Link>
      </div>
    </div>
  )
}
