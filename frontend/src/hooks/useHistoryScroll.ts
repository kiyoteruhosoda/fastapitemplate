/**
 * Coming back with the back button returns to where the reader was, on every screen (ADR-0107).
 *
 * ⚠ **The browser's own restoration does not work for this app.** Screens draw their content only
 * after the data arrives, so at the moment the browser restores, the page is only as tall as the
 * header and the position is clamped to the top. Instead we keep the position per history entry and,
 * on back/forward, **wait until the page is tall enough** before putting it back.
 *
 * Called once in the outer frame (`App`), so every screen gets it without doing anything:
 *
 * - **back/forward (POP)**: wait for the page to grow (ResizeObserver) and scroll to the kept
 *   position. Give up waiting after {@link WAIT_LIMIT_MS} (then go as far as the page allows), or as
 *   soon as the reader scrolls / taps / presses a key themselves.
 * - **opening a new screen by a link (PUSH to another path)**: start at the top.
 * - **staying on the same path** (filters in the query, replace): leave the position alone.
 *
 * ⚠ **Kept in sessionStorage, keyed by the history entry** (`location.key`), so two visits of the same
 * URL and two tabs do not overwrite each other. Where storage is unavailable it silently does
 * nothing -- the screen still works, it just starts at the top.
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import { NavigationType, useLocation, useNavigationType } from 'react-router-dom'

const PREFIX = 'history-scroll:'

/** How long a back/forward waits for the content to arrive before giving up. */
export const WAIT_LIMIT_MS = 5000

/** Events that mean "the reader is moving the page themselves": stop restoring at once. */
const USER_INPUT_EVENTS = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const

/**
 * BrowserRouter gives the first entry of a tab (no history state) the key `default`. Every fresh
 * tab and every typed URL has it, so it does not identify an entry: never keep or restore it.
 */
const NO_ENTRY_KEY = 'default'

function read(key: string): number | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key)
    const value = raw === null ? null : Number(raw)
    return value !== null && Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

function write(key: string, value: number): void {
  try {
    window.sessionStorage.setItem(PREFIX + key, String(Math.round(value)))
  } catch {
    // Storage unavailable (private window etc.): give up silently
  }
}

function canReach(target: number): boolean {
  const root = document.documentElement
  return root.scrollHeight - window.innerHeight >= target
}

/**
 * Scroll to `target` as soon as the page is tall enough. Returns a function that stops waiting.
 * `onSettled` is called exactly once, when restoring is over (done, timed out, or interrupted).
 */
function restoreWhenReachable(target: number, onSettled: () => void): () => void {
  let settled = false
  let observer: ResizeObserver | null = null
  let timer = 0

  function settle(): void {
    if (settled) return
    settled = true
    observer?.disconnect()
    window.clearTimeout(timer)
    for (const name of USER_INPUT_EVENTS) window.removeEventListener(name, interrupted, true)
    onSettled()
  }
  // The reader took over: keep whatever they are doing, do not jump afterwards
  function interrupted(): void {
    settle()
  }
  function attempt(): void {
    if (settled || !canReach(target)) return
    window.scrollTo(0, target)
    settle()
  }

  for (const name of USER_INPUT_EVENTS)
    window.addEventListener(name, interrupted, { passive: true, capture: true })
  // ⚠ Give up waiting after the limit, but still go as far down as the page allows: the data may
  //   simply be slow, and the list may also have become shorter since.
  timer = window.setTimeout(() => {
    if (settled) return
    window.scrollTo(0, target)
    settle()
  }, WAIT_LIMIT_MS)
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(attempt)
    observer.observe(document.body)
  }
  attempt()
  return settle
}

export function useHistoryScroll(): void {
  const location = useLocation()
  const navigation = useNavigationType()
  // The entry the current scroll position belongs to (null = not an identifiable entry)
  const entry = useRef<string | null>(null)
  // While waiting to restore, the page is short and its position meaningless: do not keep it
  const restoring = useRef(false)
  const lastPath = useRef<string | null>(null)

  // Take restoration over from the browser, so it does not clamp to the top and fight with us.
  useEffect(() => {
    if (!('scrollRestoration' in window.history)) return
    const previous = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    return () => {
      window.history.scrollRestoration = previous
    }
  }, [])

  // ⚠ Keep the position while scrolling, not when leaving: by the time a leaving effect runs the
  //   next screen may already be drawn and the position reset. The entry is read from a ref that
  //   is switched in the layout effect below, i.e. before the next screen's scroll events.
  useEffect(() => {
    const onScroll = () => {
      if (entry.current !== null && !restoring.current) write(entry.current, window.scrollY)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  useLayoutEffect(() => {
    const key = location.key === NO_ENTRY_KEY ? null : location.key
    const previousPath = lastPath.current
    entry.current = key
    lastPath.current = location.pathname

    if (navigation !== NavigationType.Pop) {
      // A new screen starts at the top; a change of filters on the same screen stays put.
      // A link to an anchor (#...) is left to the browser.
      if (
        navigation === NavigationType.Push &&
        previousPath !== null &&
        previousPath !== location.pathname &&
        location.hash === ''
      )
        window.scrollTo(0, 0)
      return
    }

    const target = key === null ? null : read(key)
    if (target === null) return
    restoring.current = true
    return restoreWhenReachable(target, () => {
      restoring.current = false
    })
  }, [location.key, location.pathname, location.hash, navigation])
}
