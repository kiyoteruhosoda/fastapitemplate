/**
 * Tracks "in progress" from the press until the action finishes (ADR-0080 §5).
 *
 * Adding a `busy` useState per screen makes any screen that forgets it look unresponsive.
 * Pass the in-progress flag to `ActionButton`'s `pending`; double submission is also prevented
 * here (calls while running are ignored).
 *
 * The returned `run` returns `void`, so it can be passed directly to `onSubmit` / `onClick`
 * (without tripping `no-misused-promises`).
 *
 * Errors are not swallowed (handle them inside the passed function). This only tracks whether
 * it is running, and always clears it even on failure.
 */
import { useEffect, useRef, useState } from 'react'

export function usePendingAction<A extends unknown[]>(
  action: (...args: A) => Promise<void>,
): [run: (...args: A) => void, pending: boolean] {
  const [pending, setPending] = useState(false)
  // Track running in a ref as well as state. State updates don't apply until the next render,
  // too late to catch rapid repeated presses.
  const running = useRef(false)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = (...args: A) => {
    if (running.current) return
    running.current = true
    setPending(true)
    void action(...args).finally(() => {
      running.current = false
      // Don't update after success navigated away (this component no longer exists).
      if (mounted.current) setPending(false)
    })
  }

  return [run, pending]
}
