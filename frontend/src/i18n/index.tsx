/**
 * 軽量 i18n（言語別 JSON 辞書）。
 *
 * 新規メッセージは英語キーで en.json に定義し、ja.json へ日本語訳を手動追記する
 * （CLAUDE.md「国際化」参照）。
 *
 * 選択の優先順位は「利用者の選択（localStorage）> ブラウザの言語 >
 * サーバーの既定値（DEFAULT_LOCALE）」。選べる言語は管理画面の LANGUAGES で
 * 絞り込める。
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
/** 何も選べないときに必ず使える言語（en.json が翻訳の基準）。 */
const FALLBACK_LOCALE: Locale = 'en'

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'English',
  ja: '日本語',
}

/** `{name}` 形式のプレースホルダに差し込む値。 */
export type TranslationParams = Record<string, string | number>

interface I18nValue {
  locale: Locale
  /** 選択できる言語（管理画面の LANGUAGES で絞られる）。 */
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

function initialLocale(locales: Locale[], settings: UiSettings): Locale {
  const stored = localStorage.getItem(STORAGE_KEY)
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

  // <html lang> を合わせる。読み上げソフトやブラウザの翻訳が正しく働く。
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem(STORAGE_KEY, next)
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
