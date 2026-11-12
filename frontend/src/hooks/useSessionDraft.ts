/**
 * Keeps drafts within the tab (sessionStorage) (ADR-0104).
 *
 * When an SSO sign-in can't be continued, the app moves to the sign-in screen, does a full-page
 * round trip to the IdP, then returns to the original screen. React state is lost in the round
 * trip, so **drafts are copied here on every change.** Reading them back with the same key on
 * return also reopens the input dialog that was open.
 *
 * - Removed when the value becomes `null` (saved or closed)
 * - All cleared on sign-out ({@link clearSessionDrafts}; another person may sign in on the same tab)
 * - In browsers where storage can't be read or written, behaves as plain state only
 */
import { useCallback, useState } from 'react'

const PREFIX = 'draft:'

function read<T>(key: string, initial: T | null): T | null {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + key)
    return raw === null ? initial : (JSON.parse(raw) as T)
  } catch {
    return initial
  }
}

function write(key: string, value: unknown): void {
  try {
    if (value === null) window.sessionStorage.removeItem(PREFIX + key)
    else window.sessionStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    // Even if it can't be stored, the draft remains on screen
  }
}

export function useSessionDraft<T>(key: string, initial: T | null = null) {
  const [value, setValue] = useState<T | null>(() => read<T>(key, initial))
  const update = useCallback(
    (next: T | null | ((current: T | null) => T | null)) => {
      setValue((current) => {
        const resolved =
          typeof next === 'function' ? (next as (current: T | null) => T | null)(current) : next
        write(key, resolved)
        return resolved
      })
    },
    [key],
  )
  return [value, update] as const
}

/** Clear all drafts (on sign-out). */
export function clearSessionDrafts(): void {
  try {
    for (const key of Object.keys(window.sessionStorage)) {
      if (key.startsWith(PREFIX)) window.sessionStorage.removeItem(key)
    }
  } catch {
    // Even if it can't be removed, the next save overwrites it
  }
}
