/**
 * Continue an expired session without showing a screen (ADR-0104).
 *
 * SSO sessions have no refresh token. When the access token (5 min) expires, open
 * `/api/auth/sso/renew` in a hidden frame (iframe) and ask the IdP with `prompt=none`.
 * If the IdP session is alive, the callback (`/api/auth/sso/callback`) sets new cookies and sends
 * the frame to the result page (`/api/auth/sso/renewed?result=…`). The screen reads the frame's
 * location (same origin).
 *
 * - No script runs inside the frame (no `postMessage`). The result is passed by URL only
 * - The frame stopping at the IdP's page (finished loading on an unreadable origin) or a timeout
 *   is `failed`
 * - **One at a time across tabs** (Web Locks). There is a single round-trip state cookie, so
 *   running them concurrently lets the later round trip overwrite the earlier one's cookie, and
 *   the earlier one always fails
 */

/**
 * Result page (pairs with the server's
 * `bounded_contexts/identity_federation/presentation/renewal.py`).
 */
export const RENEWAL_RESULT_PATH = '/api/auth/sso/renewed'
const START_PATH = '/api/auth/sso/renew'
const LOCK_NAME = 'sso-renewal'
/** How long to wait for the IdP round trip. After this, give up and send the user to sign-in. */
export const RENEWAL_TIMEOUT_MS = 15_000

export type RenewalResult = 'renewed' | 'declined' | 'failed'

/** Read the result from the frame's current location. null if still in progress (`about:blank`). */
function resultOf(frame: HTMLIFrameElement): RenewalResult | null {
  let location: Location | undefined
  try {
    location = frame.contentWindow?.location
    if (!location || location.href === 'about:blank') return null
    if (location.pathname !== RENEWAL_RESULT_PATH) return 'failed'
  } catch {
    // Stopped on an unreadable origin (the IdP's page). With prompt=none no page should appear
    return 'failed'
  }
  const value = new URLSearchParams(location.search).get('result')
  return value === 'renewed' || value === 'declined' ? value : 'failed'
}

/** Ask once in a hidden frame. */
export function renewInFrame(timeoutMs = RENEWAL_TIMEOUT_MS): Promise<RenewalResult> {
  return new Promise((resolve) => {
    const frame = document.createElement('iframe')
    frame.hidden = true
    frame.tabIndex = -1
    frame.setAttribute('aria-hidden', 'true')
    let settled = false
    const finish = (result: RenewalResult) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      frame.remove()
      resolve(result)
    }
    const timer = window.setTimeout(() => {
      finish('failed')
    }, timeoutMs)
    frame.addEventListener('load', () => {
      const result = resultOf(frame)
      if (result) finish(result)
    })
    frame.src = START_PATH
    document.body.appendChild(frame)
  })
}

/** Run one at a time across tabs. Without Web Locks (old browsers, http in dev) just run it. */
export async function oneAtATime<T>(task: () => Promise<T>): Promise<T> {
  const locks = (navigator as Partial<Pick<Navigator, 'locks'>>).locks
  if (!locks) return task()
  return locks.request(LOCK_NAME, task)
}
