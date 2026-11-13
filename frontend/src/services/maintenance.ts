/**
 * Receives the front tier (edge) saying it is "closed" (ADR-0080 §10).
 *
 * edge returns 503 for every request to a host with a planned-maintenance declaration, and JSON
 * to non-browsers (the default Accept of `fetch`):
 *
 *   {"error": "service_unavailable", "reason": "maintenance", "until": "…Z",
 *    "message": "<reason>", "title": "<heading>", "body": "<body text>"}
 *
 * When only the upstream (this app) is down, it is `reason: "stopped"`.
 *
 * WARNING: **Navigating never shows edge's maintenance page**, because the Service Worker
 * returns the local index.html (`navigateFallback`). So API responses switch to an in-app screen
 * instead.
 * This module only holds that state (whether closed, and what was said).
 *
 * WARNING: The app's own errors are `{"detail": {"error": …}}` and never mix with the shape above
 * (`error` and `reason` at the top level). A 503 not in that shape is not treated as "closed".
 */

export type OutageReason = 'maintenance' | 'stopped'

/** What edge said when closed. Fields without text are null (older edges have no title/body). */
export interface Outage {
  reason: OutageReason
  title: string | null
  body: string | null
  /** Why it closed (the declaration's `--reason`). */
  message: string | null
  /** Expected return time (ISO 8601, UTC). */
  until: string | null
}

/** Result of re-checking. `unknown` = unreachable or another failure; can't say closed or open. */
export type ServiceState = 'open' | 'closed' | 'unknown'

const SERVICE_UNAVAILABLE = 503

/**
 * Endpoint hit to re-check. No auth needed and light: the UI settings also read at startup.
 * Note: any path works (edge closes every path of a declared host).
 */
export const PROBE_PATH = '/api/ui/settings'

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function isOutageReason(value: unknown): value is OutageReason {
  return value === 'maintenance' || value === 'stopped'
}

/** From a 503 response body, extract only what edge said about being closed. */
export function outageFrom(status: number, payload: unknown): Outage | null {
  if (status !== SERVICE_UNAVAILABLE || !payload || typeof payload !== 'object') return null
  const body = payload as Record<string, unknown>
  if (body.error !== 'service_unavailable' || !isOutageReason(body.reason)) return null
  return {
    reason: body.reason,
    title: text(body.title),
    body: text(body.body),
    message: text(body.message),
    until: text(body.until),
  }
}

type Listener = () => void

let current: Outage | null = null
/**
 * Reload to run once it reopens, set when a lazily loaded chunk failure revealed it was closed
 * (missing chunks don't come back without a reload).
 */
let reloadOnReopen: (() => void) | null = null
const listeners = new Set<Listener>()

function sameOutage(a: Outage | null, b: Outage | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function publish(next: Outage | null): void {
  if (sameOutage(current, next)) return
  current = next
  listeners.forEach((listener) => {
    listener()
  })
}

/** Whether it is closed now (null if not). */
export function currentOutage(): Outage | null {
  return current
}

export function subscribeOutage(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** edge said it is closed. */
export function reportOutage(outage: Outage): void {
  publish(outage)
}

/** Found to be open. Reload if the screen was rendered with missing chunks. */
export function reportReopened(): void {
  const wasClosed = current !== null
  publish(null)
  const reload = reloadOnReopen
  if (wasClosed && reload) {
    reloadOnReopen = null
    reload()
  }
}

/**
 * Re-check whether it is closed. The answer is applied to the state (unchanged if unreachable).
 *
 * Note: don't use a cached answer (edge sets no-store too, but just in case).
 */
export async function checkService(): Promise<ServiceState> {
  let response: Response
  try {
    response = await fetch(PROBE_PATH, { cache: 'no-store', credentials: 'same-origin' })
  } catch {
    return 'unknown'
  }
  if (response.ok) {
    reportReopened()
    return 'open'
  }
  const outage = outageFrom(response.status, await response.json().catch(() => null))
  if (!outage) return 'unknown'
  reportOutage(outage)
  return 'closed'
}

/**
 * When a lazily loaded chunk (dynamic-import JS/CSS) fails to load, check whether it is closed.
 *
 * edge returns 503 (JSON) for JS/CSS too, so navigating while closed leaves chunks missing.
 * If closed, show the maintenance screen and reload once it reopens. **If it was just a failure,
 * do nothing** (the error is thrown as before; no `preventDefault`).
 *
 * Vite reports load failures via `vite:preloadError`.
 */
export function watchLazyLoadFailures(
  target: Window = window,
  reload: () => void = () => {
    window.location.reload()
  },
): () => void {
  const onFailure = (): void => {
    void checkService().then((state) => {
      if (state === 'closed') reloadOnReopen = reload
    })
  }
  target.addEventListener('vite:preloadError', onFailure)
  return () => {
    target.removeEventListener('vite:preloadError', onFailure)
  }
}

/** For tests: reset the state. */
export function resetOutageForTests(): void {
  current = null
  reloadOnReopen = null
  listeners.clear()
}
