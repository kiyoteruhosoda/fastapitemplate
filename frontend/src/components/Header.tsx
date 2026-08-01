import type { RefObject } from 'react'
import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'
import { RoleSwitcher } from './RoleSwitcher'

export function Header({
  navOpen,
  onToggleNav,
  toggleRef,
}: {
  navOpen: boolean
  onToggleNav: () => void
  /** ドロワーを閉じたときにフォーカスを戻す先（AppLayout が保持する）。 */
  toggleRef: RefObject<HTMLButtonElement>
}) {
  const { t } = useI18n()
  const { user, logout } = useAuth()

  return (
    <header className="header">
      <div className="header-brand">
        {/* 狭い画面だけに出るナビゲーションの開閉ボタン（表示制御は index.css）。
            開閉は aria-expanded で伝え、ラベル自体は変えない（同じボタンの名前が
            操作のたびに変わると読み上げで追いにくいため）。 */}
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
          {t('app.title')}
        </Link>
      </div>
      <div className="header-actions">
        {/* 言語・テーマの切り替えはプロフィールページにある（ADR-0016）。 */}
        {user && (
          <>
            {/* ロールの切り替え（複数ロールを持つ利用者にだけ出る。ADR-0017） */}
            <RoleSwitcher />
            <Link to="/profile" className="header-user">
              <span aria-hidden="true" className="avatar">
                {user.username.slice(0, 1).toUpperCase()}
              </span>
              <span className="header-username">{user.username}</span>
            </Link>
            <button type="button" className="button-ghost" onClick={logout}>
              {t('nav.logout')}
            </button>
          </>
        )}
      </div>
    </header>
  )
}
