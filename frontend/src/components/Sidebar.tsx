/** Navigation. Visibility is controlled by scope, not by role name. */
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
  { to: '/notes', labelKey: 'nav.notes', scopes: ['note:view'] },
]

/** Nested menu. A group is hidden together with its heading if none of its items can be shown. */
const GROUPS: Group[] = [
  {
    labelKey: 'nav.group.admin',
    items: [
      { to: '/admin/users', labelKey: 'nav.users', scopes: ['user:manage'] },
      { to: '/admin/roles', labelKey: 'nav.roles', scopes: ['role:manage'] },
      { to: '/admin/permissions', labelKey: 'nav.permissions', scopes: ['role:manage'] },
      { to: '/admin/groups', labelKey: 'nav.groups', scopes: ['group:manage'] },
      { to: '/admin/notifications', labelKey: 'nav.notifications', scopes: ['notification:send'] },
      {
        to: '/admin/content-settings',
        labelKey: 'nav.contentSettings',
        scopes: ['content-settings:view'],
      },
    ],
  },
  {
    labelKey: 'nav.group.system',
    items: [
      // Outside the tenant (ADR-0079 §1). Shown only to operators and support staff (ADR-0084)
      { to: '/system/tenants', labelKey: 'nav.tenants', scopes: ['tenant:view'] },
      { to: '/system/administrators', labelKey: 'nav.systemAdmins', scopes: ['system:manage'] },
      { to: '/admin/config', labelKey: 'nav.config', scopes: ['system-settings:view'] },
      { to: '/admin/logs', labelKey: 'nav.logs', scopes: ['log:view'] },
      { to: '/admin/audit-logs', labelKey: 'nav.auditLogs', scopes: ['audit:view'] },
      { to: '/admin/system-status', labelKey: 'nav.systemStatus', scopes: ['system:view'] },
    ],
  },
]

/**
 * *open* is the drawer state on narrow screens. On wide screens CSS always shows it, so
 * this value is passed only as the `data-open` attribute (interpreted by the media queries
 * in `index.css`).
 *
 * The close button appears only on narrow screens (the drawer covers the header, so
 * everything while it is open is done from here).
 */
export function Sidebar({
  open,
  onClose,
  navRef,
}: {
  open: boolean
  onClose: () => void
  /** Used by AppLayout to trap Tab inside this while it is open. */
  navRef: RefObject<HTMLElement | null>
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
