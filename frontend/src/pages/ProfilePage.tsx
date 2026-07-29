import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

export function ProfilePage() {
  const { t } = useI18n()
  const { user } = useAuth()
  if (!user) return null

  return (
    <div className="card">
      <h1>{t('profile.title')}</h1>
      <dl>
        <dt>{t('common.email')}</dt>
        <dd>{user.email}</dd>
        <dt>{t('common.username')}</dt>
        <dd>{user.username}</dd>
        <dt>{t('profile.scopes')}</dt>
        <dd>
          <ul className="scope-list">
            {user.scopes.map((scope) => (
              <li key={scope}>
                <code>{scope}</code>
              </li>
            ))}
          </ul>
        </dd>
      </dl>
      <div className="inline-form">
        <Link to="/change-password">{t('changePassword.title')}</Link>
        <Link to="/security">{t('security.title')}</Link>
      </div>
    </div>
  )
}
