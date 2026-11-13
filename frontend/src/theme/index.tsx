/**
 * Theme switching (light / dark / follow the OS).
 *
 * The chosen theme goes on `<html data-theme>`, and the colors are resolved by the CSS
 * variables in index.css. JavaScript only decides which palette to use; it holds no colors.
 *
 * Precedence: the user's choice (localStorage) > the server default (DEFAULT_THEME).
 * With `system`, the OS setting is followed, and OS-side changes take effect immediately.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import type { UiSettings } from '../services/uiSettings'

export type ThemePreference = 'system' | 'light' | 'dark'
/** The palette actually applied (`system` resolved). */
export type ResolvedTheme = 'light' | 'dark'

export const THEME_PREFERENCES: ThemePreference[] = ['system', 'light', 'dark']

const STORAGE_KEY = 'theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'

interface ThemeValue {
  theme: ThemePreference
  resolvedTheme: ResolvedTheme
  setTheme: (theme: ThemePreference) => void
}

const ThemeContext = createContext<ThemeValue | null>(null)

function isThemePreference(value: unknown): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark'
}

/**
 * Remembered appearance choice. ⚠ In browsers that cannot read or write storage (e.g. Chrome with
 * site data blocked), merely touching `localStorage` throws. The memo is only a convenience, so
 * carry on as if there were none.
 */
function storedTheme(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeTheme(next: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // Even if it cannot be remembered, the switch still applies on this page
  }
}

function initialTheme(settings: UiSettings): ThemePreference {
  const stored = storedTheme()
  if (isThemePreference(stored)) return stored
  return isThemePreference(settings.default_theme) ? settings.default_theme : 'system'
}

function prefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches
}

export function ThemeProvider({
  settings,
  children,
}: {
  settings: UiSettings
  children: ReactNode
}) {
  const [theme, setThemeState] = useState<ThemePreference>(() => initialTheme(settings))
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() =>
    prefersDark() ? 'dark' : 'light',
  )

  // Follow OS-side changes (keep subscribing even when something other than `system` is chosen,
  // so no stale value remains when switching back to `system` later).
  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY)
    const handle = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light')
    }
    query.addEventListener('change', handle)
    return () => {
      query.removeEventListener('change', handle)
    }
  }, [])

  const resolvedTheme: ResolvedTheme = theme === 'system' ? systemTheme : theme

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme
    // Make browser-default UI such as form controls match the palette too
    document.documentElement.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  const setTheme = useCallback((next: ThemePreference) => {
    storeTheme(next)
    setThemeState(next)
  }, [])

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  )
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used within ThemeProvider')
  return value
}
