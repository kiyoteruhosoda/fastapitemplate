import type { RefObject } from 'react'
import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'
import { AppMark } from './AppMark'
import { NotificationBell } from './NotificationBell'
import { RoleSwitcher } from './RoleSwitcher'

export function Header({
  navOpen,
  onToggleNav,
  toggleRef,
}: {
  navOpen: boolean
  onToggleNav: () => void
  /** Where focus returns when the drawer closes (held by AppLayout). */
  toggleRef: RefObject<HTMLButtonElement | null>
}) {
  const { t } = useI18n()
  const { user, logout } = useAuth()

  return (
    <header className="header">
      <div className="header-brand">
        {/* Navigation toggle shown only on narrow screens (visibility is in index.css).
            Open/closed is conveyed via aria-expanded and the label stays the same (a button
            whose name changes on each press is hard to follow with a screen reader). */}
        <button
          ref={toggleRef}
          type="button"
          className="nav-toggle"
          aria-label={t('nav.menu')}
          aria-expanded={navOpen}
          aria-controls="primary-nav"
          onClick={onToggleNav}
        >
          <span aria-hidden="true">☰</span>
        </button>
        <Link to="/" className="header-title">
          <AppMark size={28} />
          <span className="header-title-text">{t('app.title')}</span>
        </Link>
      </div>
      <div className="header-actions">
        {/* Language and theme switching live on the profile page (ADR-0080 §3). */}
        {user && (
          <>
            {/* Role switcher (shown only to users with several roles; ADR-0078 §1) */}
            <RoleSwitcher />
            {/* Announcements (ADR-0081 §3) */}
            <NotificationBell />
            <Link to="/profile" className="header-user">
              <span aria-hidden="true" className="avatar">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <span className="header-username">{user.username}</span>
            </Link>
            <button
              type="button"
              className="button-ghost"
              onClick={() => {
                void logout()
              }}
            >
              {t('nav.logout')}
            </button>
          </>
        )}
      </div>
    </header>
  )
}
