/**
 * 端末への通知（Web Push）の購読（ADR-0047）。
 *
 * ブラウザの Service Worker に購読を作らせ、その宛先（endpoint）と鍵をサーバーへ
 * 預ける。通知を受け取って出すのは Service Worker 側（`public/push-sw.js`）。
 *
 * ⚠ **購読はブラウザ単位、登録は利用者単位。** 同じブラウザで別の人がログインし直すと、
 * ブラウザには前の人の購読が残っている。「オンか」は必ずサーバーに聞く（`/push/status`）。
 */
import { api } from './api'

interface PushConfig {
  enabled: boolean
  public_key: string | null
}

export type PushState =
  /** このブラウザは Web Push を扱えない（iOS のホーム画面に追加していない Safari など）。 */
  | 'unsupported'
  /** サーバーが送れる設定になっていない。 */
  | 'unavailable'
  /** 通知を拒否されている（ブラウザの設定から戻すしかない）。 */
  | 'denied'
  | 'off'
  | 'on'

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/** base64url の公開鍵を、`pushManager.subscribe` が受け取る形へ。 */
export function applicationServerKey(publicKey: string): Uint8Array<ArrayBuffer> {
  const padded = publicKey
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .padEnd(Math.ceil(publicKey.length / 4) * 4, '=')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i)
  return bytes
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.ready
  return registration.pushManager.getSubscription()
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return 'unsupported'
  const config = await api.get<PushConfig>('/api/notifications/push')
  if (!config.enabled) return 'unavailable'
  if (Notification.permission === 'denied') return 'denied'
  const subscription = await currentSubscription()
  if (!subscription) return 'off'
  const status = await api.post<{ subscribed: boolean }>('/api/notifications/push/status', {
    endpoint: subscription.endpoint,
  })
  return status.subscribed ? 'on' : 'off'
}

/** 通知を許可してもらい、購読してサーバーへ預ける。許可されなければ `denied` を返す。 */
export async function enablePush(): Promise<PushState> {
  const config = await api.get<PushConfig>('/api/notifications/push')
  if (!config.enabled || !config.public_key) return 'unavailable'
  if ((await Notification.requestPermission()) !== 'granted') return 'denied'

  const registration = await navigator.serviceWorker.ready
  let subscription = await registration.pushManager.getSubscription()
  if (subscription) {
    // 鍵を替えたサーバーへ古い購読を預けても届かない。公開鍵が違えば作り直す。
    const current = subscription.options.applicationServerKey
    const expected = applicationServerKey(config.public_key)
    const same =
      current !== null &&
      new Uint8Array(current).length === expected.length &&
      new Uint8Array(current).every((byte, i) => byte === expected[i])
    if (!same) {
      await subscription.unsubscribe()
      subscription = null
    }
  }
  subscription ??= await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: applicationServerKey(config.public_key),
  })
  await api.post('/api/notifications/push/subscribe', subscription.toJSON())
  return 'on'
}

/** サーバーから外し、ブラウザの購読もやめる。 */
export async function disablePush(): Promise<PushState> {
  const subscription = await currentSubscription()
  if (subscription) {
    await api.post('/api/notifications/push/unsubscribe', { endpoint: subscription.endpoint })
    await subscription.unsubscribe()
  }
  return 'off'
}
