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
import { useAuth } from '../store/AuthContext'

export function SecurityPage() {
  const { t } = useI18n()
  const { user } = useAuth()
  // パスワードを持たない利用者にはフォームを出さない（ADR-0038）。出すと、
  // 「今のパスワード」を入力できない相手に、絶対に通らない入力欄を見せることになる。
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

      <div>
        <Link to="/profile">{t('security.backToProfile')}</Link>
      </div>
    </div>
  )
}
