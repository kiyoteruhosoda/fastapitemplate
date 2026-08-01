/**
 * プロフィール（本人のアカウント情報・サインインの手段・表示設定）。
 *
 * - メールアドレス・表示名はここから本人が変更できる（PUT /api/auth/me）。
 * - パスワードの変更・二要素認証・パスキーもこのページに集約する（ADR-0020）。
 * - 言語・テーマの選択もここに置く（保存先はブラウザ。ADR-0005 / ADR-0016）。
 */
import { useState, type FormEvent } from 'react'

import { PasskeyControls } from '../components/PasskeyControls'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { PreferenceControls } from '../components/PreferenceControls'
import { useToast } from '../components/ToastNotification'
import { TwoFactorControls } from '../components/TwoFactorControls'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function ProfilePage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { user, refreshMe } = useAuth()
  const [email, setEmail] = useState(user?.email ?? '')
  const [username, setUsername] = useState(user?.username ?? '')
  if (!user) return null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await api.put('/api/auth/me', { email, username })
      await refreshMe()
      notify('success', t('common.saved'))
    } catch (err) {
      notify('error', t(errorMessageKey(err)))
    }
  }

  return (
    <div className="card">
      <h1>{t('profile.title')}</h1>

      <section className="profile-section">
        <h2>{t('profile.account')}</h2>
        <form
          className="profile-form"
          onSubmit={(e) => {
            void submit(e)
          }}
        >
          <label>
            {t('common.email')}
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
              }}
              required
            />
          </label>
          <label>
            {t('common.username')}
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value)
              }}
              maxLength={100}
              required
            />
          </label>
          <button type="submit">{t('common.save')}</button>
        </form>
      </section>

      <section className="profile-section">
        <h2>{t('changePassword.title')}</h2>
        <PasswordChangeForm />
      </section>

      <section className="profile-section">
        <h2>{t('security.twoFactor')}</h2>
        <TwoFactorControls />
      </section>

      <section className="profile-section">
        <h2>{t('security.passkeys')}</h2>
        <PasskeyControls />
      </section>

      <section className="profile-section">
        <h2>{t('profile.preferences')}</h2>
        <PreferenceControls />
      </section>

      <section className="profile-section">
        <h2>{t('profile.roles')}</h2>
        <p className="hint">{t('profile.rolesHint')}</p>
        <ul className="chip-list">
          {user.roles.map((role) => (
            <li key={role}>
              <span className="chip" data-active={role === user.active_role ? 'true' : 'false'}>
                {role}
                {role === user.active_role && (
                  <span className="chip-note">{t('role.activeMark')}</span>
                )}
              </span>
            </li>
          ))}
          {user.roles.length === 0 && <li className="hint">{t('profile.noRoles')}</li>}
        </ul>
      </section>

      <section className="profile-section">
        <h2>{t('profile.scopes')}</h2>
        <p className="hint">{t('profile.scopesHint')}</p>
        <ul className="chip-list">
          {user.scopes.map((scope) => (
            <li key={scope}>
              <code className="chip chip-code">{scope}</code>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
