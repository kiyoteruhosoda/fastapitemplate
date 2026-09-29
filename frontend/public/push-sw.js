/*
 * 端末への通知（Web Push）を受けて出す（ADR-0047）。
 *
 * vite-plugin-pwa が生成する Service Worker に `importScripts` で読み込ませる
 * （`vite.config.ts` の `workbox.importScripts`）。生成物を手で直さずに済むよう、
 * 受け取りだけをこのファイルに分けている。
 *
 * 中身はサーバーの `WebPushSender` が送る形: { id, title, body, url }。
 */
/* eslint-disable no-restricted-globals */
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: event.data ? event.data.text() : '' }
  }
  const title = data.title || self.registration.scope
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(title, {
        body: data.body || '',
        icon: '/pwa-192x192.png',
        badge: '/pwa-192x192.png',
        // 同じお知らせを 2 度出さない（届き直しても置き換わる）。
        tag: data.id ? `notification-${data.id}` : undefined,
        data: { url: data.url || '/' },
      }),
      // 開いている画面にベルを取り直させる（`store/InboxContext.tsx`）。
      self.clients.matchAll({ type: 'window' }).then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'notification-received' }))
      }),
    ]),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(
    (event.notification.data && event.notification.data.url) || '/',
    self.location.origin,
  )
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      // アプリの中の行き先なら、開いている画面を使う（タブを増やさない）。
      if (target.origin === self.location.origin) {
        const existing = clients.find((client) => new URL(client.url).origin === target.origin)
        if (existing) {
          // ⚠ navigate は Service Worker が制御している画面でしか効かない。効かなければ開き直す。
          return existing
            .focus()
            .then((client) => client.navigate(target.href))
            .catch(() => self.clients.openWindow(target.href))
        }
      }
      return self.clients.openWindow(target.href)
    }),
  )
})
