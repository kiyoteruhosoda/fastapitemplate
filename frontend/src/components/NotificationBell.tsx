/**
 * ヘッダーのベル（ADR-0047）。まだ読んでいない数を出し、押すと一覧を開く。
 *
 * 一覧の 1 件を押すと既読にして行き先を開く（行き先が無ければ既読にするだけ）。
 * 開閉の作法（Esc・外側のクリックで閉じる）はロールの切り替えと揃える。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { useOpenNotificationLink } from '../hooks/useOpenNotificationLink'
import { useI18n } from '../i18n'
import { errorMessageKey } from '../services/api'
import { bellItems, type InboxItem } from '../services/notifications'
import { useInbox } from '../store/InboxContext'
import { useToast } from './ToastNotification'

/** 数の表示の上限（それ以上は「99+」）。ヘッダーの幅を数で押し広げない。 */
const BADGE_MAX = 99

export function NotificationBell() {
  const { t, locale } = useI18n()
  const { notify } = useToast()
  const { inbox, refresh, markRead, markAllRead } = useInbox()
  const openLink = useOpenNotificationLink()
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) buttonRef.current?.focus()
  }, [])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close(true)
    }
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (panelRef.current?.contains(target) ?? false) return
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

  const items = bellItems(inbox)
  const unread = inbox?.unread_count ?? 0
  const badge = unread > BADGE_MAX ? `${BADGE_MAX}+` : String(unread)

  const choose = async (item: InboxItem) => {
    try {
      if (item.read_at === null) await markRead(item.id)
      if (item.link_url) {
        close(false)
        openLink(item.link_url)
      }
    } catch (error) {
      notify('error', t(errorMessageKey(error)))
    }
  }

  const readAll = async () => {
    try {
      await markAllRead()
    } catch (error) {
      notify('error', t(errorMessageKey(error)))
    }
  }

  return (
    <div className="notification-bell">
      <button
        ref={buttonRef}
        type="button"
        className="notification-bell-toggle"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={
          unread > 0 ? t('notifications.bellUnread', { count: unread }) : t('notifications.bell')
        }
        onClick={() => {
          if (!open) void refresh()
          setOpen((value) => !value)
        }}
      >
        <BellIcon />
        {unread > 0 && (
          <span aria-hidden="true" className="notification-badge">
            {badge}
          </span>
        )}
      </button>
      {open && (
        <div
          ref={panelRef}
          className="notification-panel"
          role="dialog"
          aria-label={t('notifications.bell')}
        >
          <div className="notification-panel-head">
            <h2>{t('notifications.bell')}</h2>
            {unread > 0 && (
              <button
                type="button"
                className="button-ghost"
                onClick={() => {
                  void readAll()
                }}
              >
                {t('notifications.readAll')}
              </button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="notification-empty">{t('notifications.empty')}</p>
          ) : (
            <ul className="notification-list">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="notification-item"
                    data-unread={item.read_at === null ? 'true' : 'false'}
                    onClick={() => {
                      void choose(item)
                    }}
                  >
                    <span className="notification-item-title">
                      {item.read_at === null && (
                        <span className="notification-dot" aria-label={t('notifications.unread')} />
                      )}
                      {item.title}
                    </span>
                    {item.body && <span className="notification-item-body">{item.body}</span>}
                    <time className="notification-item-time" dateTime={item.sent_at}>
                      {new Date(item.sent_at).toLocaleString(locale)}
                    </time>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * ベルのアイコン。⚠ 絵文字（🔔）にしない ——端末ごとに色付きの絵になり、ほかの線のアイコン
 * （パスワード欄の目）と揃わない。色は `currentColor`（ボタンの文字色）に任せる。
 */
function BellIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="1.15em"
      height="1.15em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.6 1.8H4.4Z" />
      <path d="M10 20.5a2.1 2.1 0 0 0 4 0" />
    </svg>
  )
}
