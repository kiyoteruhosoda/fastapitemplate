/**
 * 画面上部のお知らせ（ADR-0047）。`banner` を含み、まだ閉じていないものの
 * いちばん新しい 1 通を本文の上に出す。
 *
 * 押すと閉じて行き先を開く。「閉じる」は閉じるだけ。どちらも既読になる。
 * トーストにしないのは、数秒で消えると見ていない間に出て消えるため
 * （新しい版の知らせと同じ考え方。ADR-0035）。
 */
import { useState } from 'react'

import { useOpenNotificationLink } from '../hooks/useOpenNotificationLink'
import { useI18n } from '../i18n'
import { errorMessageKey } from '../services/api'
import { bannerItem } from '../services/notifications'
import { useInbox } from '../store/InboxContext'
import { useToast } from './ToastNotification'

export function NotificationBanner() {
  const { t } = useI18n()
  const { notify } = useToast()
  const { inbox, dismiss } = useInbox()
  const openLink = useOpenNotificationLink()
  const [closing, setClosing] = useState(false)
  const item = bannerItem(inbox)
  if (!item) return null

  const close = async (thenOpen: boolean) => {
    if (closing) return
    setClosing(true)
    try {
      await dismiss(item.id)
      if (thenOpen) openLink(item.link_url)
    } catch (error) {
      notify('error', t(errorMessageKey(error)))
    } finally {
      setClosing(false)
    }
  }

  return (
    <div className="notification-banner" role="status">
      {item.link_url ? (
        <button
          type="button"
          className="notification-banner-text"
          disabled={closing}
          onClick={() => {
            void close(true)
          }}
        >
          <strong>{item.title}</strong>
          {item.body && <span>{item.body}</span>}
        </button>
      ) : (
        <div className="notification-banner-text">
          <strong>{item.title}</strong>
          {item.body && <span>{item.body}</span>}
        </div>
      )}
      <button
        type="button"
        className="notification-banner-close"
        aria-label={t('notifications.dismiss')}
        disabled={closing}
        onClick={() => {
          void close(false)
        }}
      >
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  )
}
