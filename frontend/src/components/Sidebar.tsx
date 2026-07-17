/** ナビゲーション。表示はロール名ではなく scope で制御する。 */
import { NavLink } from 'react-router-dom'

import { useI18n } from '../i18n'
import { useAuth } from '../store/AuthContext'

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

export function Sidebar() {
  const { t } = useI18n()
  const { hasScope } = useAuth()

  return (
    <nav className="sidebar">
      {ITEMS.filter((item) => hasScope(...item.scopes)).map((item) => (
        <NavLink key={item.to} to={item.to} end={item.to === '/'}>
          {t(item.labelKey)}
        </NavLink>
      ))}
    </nav>
  )
}
