/** ナビゲーション。表示はロール名ではなく scope で制御する。 */
import type { RefObject } from 'react'
import { NavLink } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

interface Item {
  to: string
  labelKey: string
  scopes: string[]
}

interface Group {
  labelKey: string
  items: Item[]
}

const TOP_ITEMS: Item[] = [
  { to: '/', labelKey: 'nav.dashboard', scopes: ['dashboard:view'] },
  { to: '/items', labelKey: 'nav.items', scopes: ['item:view'] },
]

/** 階層メニュー。グループは、表示できる項目が 1 つも無ければ見出しごと出さない。 */
const GROUPS: Group[] = [
  {
    labelKey: 'nav.group.admin',
    items: [
      { to: '/admin/users', labelKey: 'nav.users', scopes: ['user:manage'] },
      { to: '/admin/roles', labelKey: 'nav.roles', scopes: ['role:manage'] },
      { to: '/admin/permissions', labelKey: 'nav.permissions', scopes: ['permission:manage'] },
    ],
  },
  {
    labelKey: 'nav.group.system',
    items: [
      { to: '/admin/config', labelKey: 'nav.config', scopes: ['admin:system-settings'] },
      { to: '/admin/logs', labelKey: 'nav.logs', scopes: ['log:view'] },
      { to: '/admin/audit-logs', labelKey: 'nav.auditLogs', scopes: ['audit:view'] },
      { to: '/admin/system-status', labelKey: 'nav.systemStatus', scopes: ['system:manage'] },
    ],
  },
]

/**
 * *open* は狭い画面のドロワーの開閉。広い画面では CSS 側で常に表示されるため、
 * この値は `data-open` 属性としてだけ渡す（`index.css` のメディアクエリが解釈する）。
 *
 * 閉じるボタンは狭い画面だけに出る（ドロワーはヘッダーを覆うので、
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

  const link = (item: Item) => (
    <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={onClose}>
      {t(item.labelKey)}
    </NavLink>
  )

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
      {TOP_ITEMS.filter((item) => hasScope(...item.scopes)).map(link)}
      {GROUPS.map((group) => {
        const visible = group.items.filter((item) => hasScope(...item.scopes))
        if (visible.length === 0) return null
        return (
          <div key={group.labelKey} className="sidebar-group">
            <p className="sidebar-group-label">{t(group.labelKey)}</p>
            {visible.map(link)}
          </div>
        )
      })}
    </nav>
  )
}
