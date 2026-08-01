/**
 * プロフィール（本人のアカウント情報と表示設定。ADR-0016）。
 *
 * - メールアドレス・表示名はここから本人が変更できる（PUT /api/auth/me）。
 * - 言語・テーマの選択もここに置く（保存先はブラウザ。ADR-0005）。
 */
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { PreferenceControls } from '../components/PreferenceControls'
import { useToast } from '../components/ToastNotification'
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

      <form
        className="profile-section"
        onSubmit={(e) => {
          void submit(e)
        }}
      >
        <h2>{t('profile.account')}</h2>
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
        <div>
          <button type="submit">{t('common.save')}</button>
        </div>
      </form>

      <section className="profile-section">
        <h2>{t('profile.preferences')}</h2>
        <PreferenceControls />
      </section>

      <section className="profile-section">
        <h2>{t('profile.scopes')}</h2>
        <ul className="scope-list">
          {user.scopes.map((scope) => (
            <li key={scope}>
              <code>{scope}</code>
            </li>
          ))}
        </ul>
      </section>

      <div className="inline-form">
        <Link to="/change-password">{t('changePassword.title')}</Link>
        <Link to="/security">{t('security.title')}</Link>
      </div>
    </div>
  )
}
