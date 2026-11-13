/**
 * Lightweight i18n (one JSON dictionary per language).
 *
 * Define new messages in en.json under English keys, and add the Japanese translation to
 * ja.json by hand (see the 国際化（i18n） section of CLAUDE.md).
 *
 * Precedence: the user's choice (localStorage) > the browser language >
 * the server default (DEFAULT_LOCALE). The selectable languages can be narrowed with
 * LANGUAGES on the admin screen.
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
import en from './en.json'
import ja from './ja.json'

export type Locale = 'en' | 'ja'

const DICTIONARIES: Record<Locale, Record<string, string>> = { en, ja }
const STORAGE_KEY = 'locale'
/** Always-available language when nothing else can be chosen (en.json is the translation baseline). */
const FALLBACK_LOCALE: Locale = 'en'

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  ja: '日本語',
}

/** Values substituted into `{name}`-style placeholders. */
export type TranslationParams = Record<string, string | number>

interface I18nValue {
  locale: Locale
  /** Selectable languages (narrowed by LANGUAGES on the admin screen). */
  locales: Locale[]
  setLocale: (locale: Locale) => void
  t: (key: string, params?: TranslationParams) => string
}

const I18nContext = createContext<I18nValue | null>(null)

function isLocale(value: unknown): value is Locale {
  return value === 'en' || value === 'ja'
}

function availableLocales(settings: UiSettings): Locale[] {
  const configured = settings.languages.filter(isLocale)
  return configured.length > 0 ? configured : [FALLBACK_LOCALE]
}

/**
 * Remembered language choice. ⚠ In browsers that cannot read or write storage (e.g. Chrome with
 * site data blocked), merely touching `localStorage` throws. The memo is only a convenience, so
 * carry on as if there were none.
 */
function storedLocale(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeLocale(next: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // Even if it cannot be remembered, the switch still applies on this page
  }
}

function initialLocale(locales: Locale[], settings: UiSettings): Locale {
  const stored = storedLocale()
  if (isLocale(stored) && locales.includes(stored)) return stored

  const fromBrowser = navigator.language.split('-')[0]
  if (isLocale(fromBrowser) && locales.includes(fromBrowser)) return fromBrowser

  const fromServer = settings.default_locale
  if (isLocale(fromServer) && locales.includes(fromServer)) return fromServer
  return locales[0] ?? FALLBACK_LOCALE
}

function interpolate(template: string, params?: TranslationParams): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  )
}

export function I18nProvider({
  settings,
  children,
}: {
  settings: UiSettings
  children: ReactNode
}) {
  const locales = useMemo(() => availableLocales(settings), [settings])
  const [locale, setLocaleState] = useState<Locale>(() => initialLocale(locales, settings))

  // Keep <html lang> in sync so screen readers and browser translation work correctly.
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  const setLocale = useCallback((next: Locale) => {
    storeLocale(next)
    setLocaleState(next)
  }, [])

  const t = useCallback(
    (key: string, params?: TranslationParams) =>
      interpolate(DICTIONARIES[locale][key] ?? DICTIONARIES.en[key] ?? key, params),
    [locale],
  )

  const value = useMemo(() => ({ locale, locales, setLocale, t }), [locale, locales, setLocale, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used within I18nProvider')
  return value
}
