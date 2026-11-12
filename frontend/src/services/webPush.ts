/**
 * Subscribing to device notifications (Web Push) (ADR-0081 §3).
 *
 * Has the browser's Service Worker create a subscription and hands its destination (endpoint)
 * and keys to the server. Receiving and showing notifications is the Service Worker's job
 * (`public/push-sw.js`).
 *
 * WARNING: **Subscriptions are per browser; registrations are per user.** If someone else signs
 * in on the same browser, the previous user's subscription remains. Always ask the server whether
 * it is on (`/push/status`).
 */
import { api } from './api'

interface PushConfig {
  enabled: boolean
  public_key: string | null
}

export type PushState =
  /** This browser can't handle Web Push (e.g. Safari on iOS not added to the home screen). */
  | 'unsupported'
  /** The server isn't configured to send. */
  | 'unavailable'
  /** Notifications are denied (only the browser settings can undo it). */
  | 'denied'
  | 'off'
  | 'on'

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/** Convert a base64url public key into the form `pushManager.subscribe` accepts. */
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

/** Ask for permission, subscribe, and hand it to the server. Returns `denied` if not allowed. */
export async function enablePush(): Promise<PushState> {
  const config = await api.get<PushConfig>('/api/notifications/push')
  if (!config.enabled || !config.public_key) return 'unavailable'
  if ((await Notification.requestPermission()) !== 'granted') return 'denied'

  const registration = await navigator.serviceWorker.ready
  let subscription = await registration.pushManager.getSubscription()
  if (subscription) {
    // An old subscription handed to a server whose key changed won't deliver. Recreate it if the
    // public key differs.
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

/** Remove it from the server and unsubscribe the browser too. */
export async function disablePush(): Promise<PushState> {
  const subscription = await currentSubscription()
  if (subscription) {
    await api.post('/api/notifications/push/unsubscribe', { endpoint: subscription.endpoint })
    await subscription.unsubscribe()
  }
  return 'off'
}
