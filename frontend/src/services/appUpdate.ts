/**
 * Detect that a new version has been built (Service Worker update).
 *
 * The SPA only re-renders and never reloads, so **after a deploy, devices left open keep running
 * the old version**. The Service Worker fetches the new version in the background, but has no way
 * to replace JavaScript already loaded (replacement takes effect from the next load). So we only
 * tell the screen that "a new version is waiting", and the swap (= reload) happens when the user
 * presses the button (ADR-0080 §7).
 *
 * WARNING: Just waiting won't notice it. Browsers check for Service Worker updates **on page
 * navigation**, and SPA screen changes are not page navigations. So we trigger the check here
 * periodically and when the tab returns to the foreground.
 */
import { registerSW } from 'virtual:pwa-register'

/** Interval between update checks. */
export const UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000

/** Minimum interval between checks (don't hit it often even if the tab keeps going in and out). */
const MIN_CHECK_GAP_MS = 60 * 1000

/**
 * Grace period after the press before we reload on our own.
 *
 * Normally workbox reloads on the signal that the new Service Worker took control
 * (`controllerchange`). WARNING: **On a screen not yet controlled by a Service Worker** — a tab
 * that opened this version for the first time (right after registration) — the signal never
 * comes, so pressing would do nothing. This catches that case.
 */
const RELOAD_FALLBACK_MS = 2000

/** Swap to the new version (reload the current screen). */
export type ApplyUpdate = () => void

/** Called when a new version is waiting. */
export type UpdateReadyListener = (apply: ApplyUpdate) => void

/** Watch for a waiting new version. */
export type WatchForUpdate = (onUpdateReady: UpdateReadyListener) => void

function scheduleChecks(registration: ServiceWorkerRegistration): void {
  let checkedAt = 0

  const check = (): void => {
    const now = Date.now()
    // Don't trigger while fetching, offline, or just checked.
    if (registration.installing || !navigator.onLine || now - checkedAt < MIN_CHECK_GAP_MS) return
    checkedAt = now
    void registration.update().catch(() => {
      // Even if the check fails, don't show it on screen (retry at the next chance).
    })
  }

  setInterval(check, UPDATE_CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') check()
  })
}

export const watchForUpdate: WatchForUpdate = (onUpdateReady) => {
  const updateSW = registerSW({
    onNeedRefresh() {
      onUpdateReady(() => {
        // Send skipWaiting to the waiting Service Worker. workbox reloads
        // on the signal that control has moved.
        void updateSW()
        window.setTimeout(() => {
          window.location.reload()
        }, RELOAD_FALLBACK_MS)
      })
    },
    onRegisteredSW(_swUrl, registration) {
      if (registration) scheduleChecks(registration)
    },
  })
}
