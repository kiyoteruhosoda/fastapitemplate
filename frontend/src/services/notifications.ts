/**
 * Notifications (ADR-0081 §3) API, plus small checks the screens use.
 *
 * Where a notification appears is decided by `channels`.
 * - `bell`   … the header bell (stays in the list; counted until marked read)
 * - `banner` … top of the screen (shown until closed or clicked)
 * - `push`   … device notification (Web Push; `services/webPush.ts`)
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
  users: { id: number; username: string; email: string | null }[]
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

/** What goes in the bell list. */
export function bellItems(inbox: Inbox | null): InboxItem[] {
  return (inbox?.items ?? []).filter((item) => item.channels.includes('bell'))
}

/** What goes at the top of the screen (only the newest one is shown). */
export function bannerItem(inbox: Inbox | null): InboxItem | null {
  return (
    (inbox?.items ?? []).find(
      (item) => item.channels.includes('banner') && item.dismissed_at === null,
    ) ?? null
  )
}

/**
 * Whether the destination is inside this app (`/items`). Inside opens via screen switch; outside
 * opens in another tab. WARNING: `//host` looks like a path but is another host, so it counts as
 * outside (the server rejects it, but the screen doesn't rely on that either).
 */
export function isInAppLink(link: string): boolean {
  return link.startsWith('/') && !link.startsWith('//')
}
