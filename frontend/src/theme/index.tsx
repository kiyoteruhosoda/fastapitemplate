/**
 * テーマ切り替え（ライト / ダーク / OS 追従）。
 *
 * 選んだテーマは `<html data-theme>` に載せ、配色は index.css の CSS 変数で
 * 解決する。JavaScript 側は「どの配色を使うか」だけを決め、色そのものは持たない。
 *
 * 優先順位は「利用者の選択（localStorage）> サーバーの既定値（DEFAULT_THEME）」。
 * `system` を選んだ場合は OS の設定に追従し、OS 側の切り替えにも即座に反応する。
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
/** 実際に適用される配色（`system` を解決した結果）。 */
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

function initialTheme(settings: UiSettings): ThemePreference {
  const stored = localStorage.getItem(STORAGE_KEY)
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

  // OS 側の切り替えに追従する（`system` 以外を選んでいても購読は続ける。
  // 途中で `system` に戻したときに古い値が残らないようにするため）。
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
    // フォームコントロール等のブラウザ既定 UI も配色に合わせる
    document.documentElement.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  const setTheme = useCallback((next: ThemePreference) => {
    localStorage.setItem(STORAGE_KEY, next)
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
