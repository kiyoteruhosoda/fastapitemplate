import { Link } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'
import { PreferenceControls } from './PreferenceControls'

export function Header({ navOpen, onToggleNav }: { navOpen: boolean; onToggleNav: () => void }) {
  const { t } = useI18n()
  const { user, logout } = useAuth()

  return (
    <header className="header">
      <div className="header-brand">
        {/* 狭い画面だけに出るナビゲーションの開閉ボタン（表示制御は index.css）。
            開閉は aria-expanded で伝え、ラベル自体は変えない（同じボタンの名前が
            操作のたびに変わると読み上げで追いにくいため）。 */}
        <button
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
        {/* 言語・テーマは狭い画面ではドロワー側（.sidebar-preferences）に出る。 */}
        <div className="header-preferences">
          <PreferenceControls />
        </div>
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
