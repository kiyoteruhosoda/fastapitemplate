/**
 * Profile (the user's own account information and display settings. ADR-0080 §3).
 *
 * - The user can change their email address and display name here (PUT /api/auth/me). For
 *   users linked to an IdP they are overwritten at the next login, so no input is shown and
 *   they are directed to the IdP (ADR-0094).
 * - Language and theme selection is also here (stored in the browser. ADR-0080 §1).
 * - Sign-in methods (password, two-factor authentication, passkeys) are on a separate page
 *   (`/profile/security`). Only the entry point is shown here (ADR-0080 §4).
 */
import { useState, type SubmitEvent } from 'react'
import { Link } from 'react-router-dom'

import { ActionButton } from '../components/ActionButton'
import { PreferenceControls } from '../components/PreferenceControls'
import { PushNotificationControls } from '../components/PushNotificationControls'
import { useToast } from '../components/ToastNotification'
import { usePendingAction } from '../hooks/usePendingAction'
import { useReauthentication } from '../hooks/useReauthentication'
import { useI18n } from '../i18n'
import { api, errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'

export function ProfilePage() {
  const { t } = useI18n()
  const { notify } = useToast()
  const reauthenticate = useReauthentication()
  const { user, refreshMe } = useAuth()
  const [email, setEmail] = useState(user?.email ?? '')
  const [username, setUsername] = useState(user?.username ?? '')

  const [submit, submitting] = usePendingAction(async (e: SubmitEvent) => {
    e.preventDefault()
    try {
      await api.put('/api/auth/me', { email, username })
      await refreshMe()
      notify('success', t('common.saved'))
    } catch (err) {
      if (reauthenticate(err)) return
      notify('error', t(errorMessageKey(err)))
    }
  })

  if (!user) return null

  return (
    <div className="card">
      <h1>{t('profile.title')}</h1>

      <section className="settings-section">
        <h2>{t('profile.account')}</h2>
        {user.profile_managed_by_idp ? (
          <>
            <p>
              {t('common.email')}: {user.email}
            </p>
            <p>
              {t('common.username')}: {user.username}
            </p>
            <p className="hint">{t('profile.managedByIdp')}</p>
          </>
        ) : (
          <form className="settings-form" onSubmit={submit}>
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
            <ActionButton type="submit" pending={submitting}>
              {t('common.save')}
            </ActionButton>
          </form>
        )}
      </section>

      <section className="settings-section">
        <h2>{t('security.title')}</h2>
        <p className="hint">{t('security.hint')}</p>
        <Link to="/profile/security" className="button-link">
          {t('security.open')}
        </Link>
      </section>

      <section className="settings-section">
        <h2>{t('profile.preferences')}</h2>
        <PreferenceControls />
      </section>

      <section className="settings-section">
        <h2>{t('push.title')}</h2>
        <PushNotificationControls />
      </section>

      <section className="settings-section">
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

      <section className="settings-section">
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
