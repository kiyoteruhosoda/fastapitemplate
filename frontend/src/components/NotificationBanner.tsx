/**
 * Announcement at the top of the screen (ADR-0081 §3). Shows the newest one that includes
 * `banner` and has not been dismissed yet, above the main content.
 *
 * Clicking it dismisses it and opens its destination. "Close" only dismisses. Both mark it read.
 * It is not a toast because a toast vanishes after a few seconds and can appear and disappear
 * while the user is not looking (same reasoning as the new-version notice, ADR-0080 §7).
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
