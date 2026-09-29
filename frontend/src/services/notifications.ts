/**
 * お知らせ（ADR-0047）の API と、画面が使う小さな判定。
 *
 * 1 通のお知らせは `channels` で出る場所が決まる。
 * - `bell`   … ヘッダーのベル（一覧に残る。既読にするまで数に出る）
 * - `banner` … 画面の上部（閉じるか押すまで出続ける）
 * - `push`   … 端末への通知（Web Push。`services/webPush.ts`）
 */
import { api } from './api'

export type Channel = 'bell' | 'banner' | 'push'
export type AudienceKind = 'all' | 'group' | 'user'

export interface Audience {
  kind: AudienceKind
  target_id: number | null
}

export interface NotificationBase {
  id: number
  title: string
  body: string
  link_url: string | null
  channels: Channel[]
  sent_at: string
}

export interface InboxItem extends NotificationBase {
  read_at: string | null
  dismissed_at: string | null
}

export interface Inbox {
  items: InboxItem[]
  unread_count: number
}

export interface SentNotification {
  notification: NotificationBase
  audience: Audience
  recipient_count: number
  read_count: number
}

export interface SendResult {
  notification: NotificationBase
  audience: Audience
  recipient_count: number
  push_scheduled: boolean
}

export interface SendRequest {
  title: string
  body: string
  link_url: string | null
  channels: Channel[]
  audience: Audience
}

export interface AudienceOptions {
  groups: { id: number; name: string; member_count: number }[]
  users: { id: number; username: string; email: string }[]
}

export const notificationsApi = {
  inbox: () => api.get<Inbox>('/api/notifications'),
  markRead: (id: number) => api.post<undefined>(`/api/notifications/${id}/read`),
  markAllRead: () => api.post<undefined>('/api/notifications/read-all'),
  dismiss: (id: number) => api.post<undefined>(`/api/notifications/${id}/dismiss`),
  send: (request: SendRequest) => api.post<SendResult>('/api/admin/notifications', request),
  sent: () => api.get<SentNotification[]>('/api/admin/notifications'),
  audiences: () => api.get<AudienceOptions>('/api/admin/notifications/audiences'),
}

/** ベルの一覧に出すもの。 */
export function bellItems(inbox: Inbox | null): InboxItem[] {
  return (inbox?.items ?? []).filter((item) => item.channels.includes('bell'))
}

/** 画面上部に出すもの（新しい順の先頭 1 通だけを出す）。 */
export function bannerItem(inbox: Inbox | null): InboxItem | null {
  return (
    (inbox?.items ?? []).find(
      (item) => item.channels.includes('banner') && item.dismissed_at === null,
    ) ?? null
  )
}

/**
 * 行き先がこのアプリの中か（`/items`）。中なら画面の切り替えで開き、外なら
 * 別のタブで開く。⚠ `//host` はパスに見えて別のホストなので外として扱う
 * （サーバーは受け付けないが、画面でも前提にしない）。
 */
export function isInAppLink(link: string): boolean {
  return link.startsWith('/') && !link.startsWith('//')
}
