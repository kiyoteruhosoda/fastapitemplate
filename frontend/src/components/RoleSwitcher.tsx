/**
 * Active role switcher (ADR-0078 §1).
 *
 * Lets a user with several roles choose which role they are acting as. The default is
 * "All roles" (the union of their permissions); choosing one narrows to that role's
 * permissions only. Switching reissues the token, so right after the click both the items
 * on screen (Sidebar) and the scope of the tokens sent are in sync.
 *
 * Renders nothing for users with one role or fewer (there is nothing to choose, and "All"
 * and that single role grant the same permissions).
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { useI18n } from '../i18n'
import { errorMessageKey } from '../services/api'
import { useAuth } from '../store/AuthContext'
import { ActionButton } from './ActionButton'
import { useToast } from './ToastNotification'

export function RoleSwitcher() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { user, switchRole } = useAuth()
  const [open, setOpen] = useState(false)
  // Selection being switched to (the spinner shows only on the clicked item). "All roles"
  // is `role: null`, so keep the whole wrapper to tell it apart from "nothing selected".
  const [switchingTo, setSwitchingTo] = useState<{ role: string | null } | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  // While open, Esc and outside clicks close it. Esc returns focus to the button being
  // operated; an outside click leaves focus where the user clicked.
  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close(true)
    }
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (menuRef.current?.contains(target) ?? false) return
      if (buttonRef.current?.contains(target) ?? false) return
      close(false)
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('mousedown', onPointerDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('mousedown', onPointerDown)
    }
  }, [open, close])

  // Render nothing when there is nothing to choose (all hooks are called before this check).
  if (!user || user.roles.length < 2) return null

  const activeLabel = user.active_role ?? t('role.all')

  const select = async (role: string | null) => {
    if (role === user.active_role) {
      close(true)
      return
    }
    if (switchingTo) return
    setSwitchingTo({ role })
    try {
      await switchRole(role)
      notify('success', t('role.switched', { role: role ?? t('role.all') }))
      close(true)
    } catch (error) {
      notify('error', t(errorMessageKey(error)))
    } finally {
      setSwitchingTo(null)
    }
  }

  const option = (role: string | null) => {
    const label = role ?? t('role.all')
    const current = role === user.active_role
    return (
      <ActionButton
        key={label}
        type="button"
        role="menuitemradio"
        aria-checked={current}
        className="role-switcher-option"
        pending={switchingTo !== null && switchingTo.role === role}
        disabled={switchingTo !== null}
        onClick={() => {
          void select(role)
        }}
      >
        <span aria-hidden="true" className="role-switcher-check">
          {current ? '✓' : ''}
        </span>
        {label}
      </ActionButton>
    )
  }

  return (
    <div className="role-switcher">
      <button
        ref={buttonRef}
        type="button"
        className="role-switcher-toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value)
        }}
      >
        <span className="role-switcher-label">{t('role.active')}</span>
        <span className="role-switcher-value">{activeLabel}</span>
        <span aria-hidden="true" className="role-switcher-caret">
          ▾
        </span>
      </button>
      {open && (
        <div ref={menuRef} className="role-switcher-menu" role="menu" aria-label={t('role.switch')}>
          <p className="role-switcher-hint">{t('role.hint')}</p>
          {option(null)}
          {user.roles.map((role) => option(role))}
        </div>
      )}
    </div>
  )
}
