/**
 * 本人の手元のお知らせ（ADR-0047）。ベル（ヘッダー）と画面上部の知らせが同じ一覧を
 * 見るので、取得と既読・閉じるをここに集める。
 *
 * 取り直すのは、開いたとき・一定間隔・タブが手前に戻ったとき・端末への通知が
 * 届いたとき（Service Worker からの合図。`public/push-sw.js`）。
 * 取れなかったときは黙って前の一覧のまま（ベルが出ないだけで、画面の操作は止めない）。
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

/** 取り直す間隔。お知らせは急ぎのものではないので、1 分で十分。 */
export const INBOX_REFRESH_INTERVAL_MS = 60 * 1000

/** Service Worker が「端末への通知が届いた」と画面へ伝える合図の名前。 */
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
      // 取れなくても画面は止めない（次の機会に取り直す）。
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
    // Service Worker は安全な接続（https / localhost）でしか使えない。
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
  if (!value) throw new Error('useInbox は InboxProvider の内側で使う')
  return value
}
