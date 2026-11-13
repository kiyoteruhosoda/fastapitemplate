/**
 * The user's own notification inbox (ADR-0081 §3). The bell (header) and the banner at the top
 * of the screen read the same list, so fetching, marking read and dismissing live here.
 *
 * It is re-fetched on open, at a fixed interval, when the tab comes back to the foreground, and
 * when a device notification arrives (a signal from the Service Worker; `public/push-sw.js`).
 * On failure it silently keeps the previous list (only the bell is missing; the UI keeps working).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { notificationsApi, type Inbox } from '../services/notifications'

/** Re-fetch interval. Notifications are not urgent, so one minute is enough. */
export const INBOX_REFRESH_INTERVAL_MS = 60 * 1000

/** Name of the message the Service Worker sends the page when a device notification arrives. */
export const PUSH_RECEIVED_MESSAGE = 'notification-received'

interface InboxValue {
  inbox: Inbox | null
  refresh: () => Promise<void>
  markRead: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  dismiss: (id: number) => Promise<void>
}

const InboxContext = createContext<InboxValue | null>(null)

export function InboxProvider({ children }: { children: ReactNode }) {
  const [inbox, setInbox] = useState<Inbox | null>(null)

  const refresh = useCallback(async () => {
    try {
      setInbox(await notificationsApi.inbox())
    } catch {
      // A failed fetch does not block the UI (it is retried next time).
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => {
      void refresh()
    }, INBOX_REFRESH_INTERVAL_MS)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    const onMessage = (event: MessageEvent) => {
      if ((event.data as { type?: unknown } | null)?.type === PUSH_RECEIVED_MESSAGE) void refresh()
    }
    // Service Workers are only available on secure origins (https / localhost).
    const worker = 'serviceWorker' in navigator ? navigator.serviceWorker : null
    document.addEventListener('visibilitychange', onVisible)
    worker?.addEventListener('message', onMessage)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      worker?.removeEventListener('message', onMessage)
    }
  }, [refresh])

  const markRead = useCallback(
    async (id: number) => {
      await notificationsApi.markRead(id)
      await refresh()
    },
    [refresh],
  )

  const markAllRead = useCallback(async () => {
    await notificationsApi.markAllRead()
    await refresh()
  }, [refresh])

  const dismiss = useCallback(
    async (id: number) => {
      await notificationsApi.dismiss(id)
      await refresh()
    },
    [refresh],
  )

  const value = useMemo(
    () => ({ inbox, refresh, markRead, markAllRead, dismiss }),
    [inbox, refresh, markRead, markAllRead, dismiss],
  )
  return <InboxContext.Provider value={value}>{children}</InboxContext.Provider>
}

export function useInbox(): InboxValue {
  const value = useContext(InboxContext)
  if (!value) throw new Error('useInbox must be used within InboxProvider')
  return value
}
