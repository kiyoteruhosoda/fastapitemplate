/**
 * When the sign-in screen opens and the user is already signed in at the IdP, sign them in
 * without a click (ADR-0077 §9).
 *
 * Before rendering, send the browser to the IdP with `prompt=none`. If signed in there, a code
 * comes back and the user signs in the same way as normal SSO; if not, the IdP returns without
 * showing a screen (the server sends the user back to the sign-in screen with
 * `?sso_silent=declined`).
 *
 * When not to try (prevents loops and unrequested re-sign-ins):
 *
 * - **After signing out.** Sign-out does not end the IdP SSO session by default, so trying would
 *   sign the user straight back in. Marked in `localStorage` (other tabs don't try either)
 * - **After trying once in this tab.** Marked in `sessionStorage`
 * - When the sign-in URL carries anything other than the destination (`redirect_to`) (an error, a
 *   sign-out notice, the tried marker)
 *
 * However, **when the user reloads, try once more even if this tab's marker and the tried marker
 * (`sso_silent`) are present** (they signed in at the IdP in another tab and came back;
 * ADR-0077 §10).
 * Being sent back after a decline is not a reload, so this does not loop. The sign-out marker and
 * error notices are respected even on reload.
 *
 * Both markers are **cleared on sign-in** through any entry point (so we try again the next time
 * the session expires).
 *
 * WARNING: **Do not try in browsers where the markers can't be written.** Trying without them
 * means we can't tell on return that we already tried, and the redirects never stop.
 */
import { REDIRECT_TO_PARAM } from './returnTo'

const TRIED_KEY = 'ssoSilentTried'
const SIGNED_OUT_KEY = 'ssoSignedOut'
/** Marker that we tried and were declined (set by the server). Even if present, retry on reload. */
const SILENT_DECLINED_PARAM = 'sso_silent'

/** Whether this page was opened by the user reloading. */
function openedByReload(): boolean {
  try {
    const [entry] = window.performance.getEntriesByType(
      'navigation',
    ) as PerformanceNavigationTiming[]
    return entry?.type === 'reload'
  } catch {
    return false
  }
}

/** Whether trying is allowed, judging by this page's URL query and the markers (sets none). */
export function maySilentSso(params: URLSearchParams, reloaded = openedByReload()): boolean {
  for (const name of params.keys()) {
    if (name === REDIRECT_TO_PARAM || (reloaded && name === SILENT_DECLINED_PARAM)) continue
    return false
  }
  try {
    if (window.localStorage.getItem(SIGNED_OUT_KEY)) return false
    return reloaded || !window.sessionStorage.getItem(TRIED_KEY)
  } catch {
    return false
  }
}

/**
 * Set the "tried in this tab" marker just before redirecting. Returns false if it can't be set
 * (then don't try).
 */
export function markSilentSsoTried(): boolean {
  try {
    window.sessionStorage.setItem(TRIED_KEY, '1')
    return window.sessionStorage.getItem(TRIED_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * Whether the signed-out marker is set (also skips queries to continue an expired session;
 * ADR-0104). True if unreadable.
 */
export function signedOutHere(): boolean {
  try {
    return window.localStorage.getItem(SIGNED_OUT_KEY) !== null
  } catch {
    return true
  }
}

/** Signed out. Don't try the next time the sign-in screen opens. */
export function markSignedOut(): void {
  try {
    window.localStorage.setItem(SIGNED_OUT_KEY, '1')
  } catch {
    // Browsers that can't write never try in the first place (markSilentSsoTried)
  }
}

/** Signed in. Clear the markers so we try again the next time the session expires. */
export function clearSilentSsoMarks(): void {
  try {
    window.localStorage.removeItem(SIGNED_OUT_KEY)
    window.sessionStorage.removeItem(TRIED_KEY)
  } catch {
    // Signed in even if they can't be cleared
  }
}
