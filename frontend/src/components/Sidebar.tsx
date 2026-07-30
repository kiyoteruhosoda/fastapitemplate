/** ナビゲーション。表示はロール名ではなく scope で制御する。 */
import type { RefObject } from 'react'
import { NavLink } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'
import { PreferenceControls } from './PreferenceControls'

interface Item {
  to: string
  labelKey: string
  scopes: string[]
}

const ITEMS: Item[] = [
  { to: '/', labelKey: 'nav.dashboard', scopes: ['dashboard:view'] },
  { to: '/items', labelKey: 'nav.items', scopes: ['item:view'] },
  { to: '/admin/users', labelKey: 'nav.users', scopes: ['user:manage'] },
  { to: '/admin/roles', labelKey: 'nav.roles', scopes: ['role:manage'] },
  { to: '/admin/permissions', labelKey: 'nav.permissions', scopes: ['permission:manage'] },
  { to: '/admin/config', labelKey: 'nav.config', scopes: ['admin:system-settings'] },
  { to: '/admin/logs', labelKey: 'nav.logs', scopes: ['log:view'] },
]

/**
 * *open* は狭い画面のドロワーの開閉。広い画面では CSS 側で常に表示されるため、
 * この値は `data-open` 属性としてだけ渡す（`index.css` のメディアクエリが解釈する）。
 *
 * 閉じるボタンと言語・テーマの選択は狭い画面だけに出る（ドロワーはヘッダーを覆うので、
 * 開いているあいだの操作をここで完結させる）。
 */
export function Sidebar({
  open,
  onClose,
  navRef,
}: {
  open: boolean
  onClose: () => void
  /** 開いているあいだ Tab をこの中に閉じ込めるために AppLayout が使う。 */
  navRef: RefObject<HTMLElement>
}) {
  const { t } = useI18n()
  const { hasScope } = useAuth()

  return (
    <nav
      ref={navRef}
      id="primary-nav"
      className="sidebar"
      data-open={open ? 'true' : 'false'}
      aria-label={t('nav.menu')}
    >
      <button
        type="button"
        className="sidebar-close"
        aria-label={t('nav.closeMenu')}
        onClick={onClose}
      >
        <span aria-hidden="true">✕</span>
      </button>
      {ITEMS.filter((item) => hasScope(...item.scopes)).map((item) => (
        <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={onClose}>
          {t(item.labelKey)}
        </NavLink>
      ))}
      <div className="sidebar-preferences">
        <PreferenceControls />
      </div>
    </nav>
  )
}
