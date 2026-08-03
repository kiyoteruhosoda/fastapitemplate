/**
 * アクティブロールの切り替え（ADR-0017）。
 *
 * 複数のロールを持つ利用者が「いまどのロールで操作しているか」を選ぶ。既定は
 * 「すべてのロール」（保有権限の和集合）で、1 つを選ぶとそのロールの権限だけに
 * 絞られる。切り替えはトークンの再発行なので、押した直後から画面に出る項目
 * （Sidebar）も送るトークンの scope も揃う。
 *
 * ロールが 1 つ以下の利用者には何も出さない（選べる先が無く、「すべて」と
 * その 1 つは同じ権限になるため）。
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
  // 切り替え中の選択（押した項目にだけスピナーを出す）。「すべてのロール」は
  // `role: null` なので、選んでいない状態と区別できるよう入れ物ごと持つ。
  const [switchingTo, setSwitchingTo] = useState<{ role: string | null } | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  // 開いているあいだは Esc と外側のクリックで閉じる。Esc は「いま操作している
  // ボタン」へフォーカスを戻し、外側のクリックは押した先へフォーカスを譲る。
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

  // 選べる先が無いなら出さない（hooks はこの判定より前に呼び切る）。
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
