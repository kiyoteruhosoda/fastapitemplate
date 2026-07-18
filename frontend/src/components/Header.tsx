import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

export function Header() {
  const { t, locale, setLocale } = useI18n()
  const { user, logout } = useAuth()

  return (
    <header className="header">
      <Link to="/" className="header-title">
        {t('app.title')}
      </Link>
      <div className="header-actions">
        <select value={locale} onChange={(e) => setLocale(e.target.value as 'en' | 'ja')}>
          <option value="en">English</option>
          <option value="ja">日本語</option>
        </select>
        {user && (
          <>
            <Link to="/profile">{user.username}</Link>
            <button onClick={logout}>{t('nav.logout')}</button>
          </>
        )}
      </div>
    </header>
  )
}
