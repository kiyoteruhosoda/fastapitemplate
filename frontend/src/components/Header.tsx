import { Link } from 'react-router-dom'

import { LOCALE_LABELS, useI18n, type Locale } from '../i18n'
import { useAuth } from '../store/AuthContext'
import { THEME_PREFERENCES, useTheme, type ThemePreference } from '../theme'

export function Header() {
  const { t, locale, locales, setLocale } = useI18n()
  const { theme, setTheme } = useTheme()
  const { user, logout } = useAuth()

  return (
    <header className="header">
      <Link to="/" className="header-title">
        {t('app.title')}
      </Link>
      <div className="header-actions">
        <select
          aria-label={t('common.language')}
          value={locale}
          onChange={(e) => {
            setLocale(e.target.value as Locale)
          }}
        >
          {locales.map((value) => (
            <option key={value} value={value}>
              {LOCALE_LABELS[value]}
            </option>
          ))}
        </select>
        <select
          aria-label={t('common.theme')}
          value={theme}
          onChange={(e) => {
            setTheme(e.target.value as ThemePreference)
          }}
        >
          {THEME_PREFERENCES.map((value) => (
            <option key={value} value={value}>
              {t(`theme.${value}`)}
            </option>
          ))}
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
