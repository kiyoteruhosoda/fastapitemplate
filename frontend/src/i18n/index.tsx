/**
 * 軽量 i18n（言語別 JSON 辞書）。
 *
 * 新規メッセージは英語キーで en.json に定義し、ja.json へ日本語訳を手動追記する
 * （CLAUDE.md「国際化」参照）。
 */
import { createContext, useContext, useState, type ReactNode } from 'react'

import en from './en.json'
import ja from './ja.json'

type Locale = 'en' | 'ja'
const DICTIONARIES: Record<Locale, Record<string, string>> = { en, ja }
const STORAGE_KEY = 'locale'

interface I18nValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: string) => string
}

const I18nContext = createContext<I18nValue | null>(null)

function initialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'en' || stored === 'ja') return stored
  return navigator.language.startsWith('ja') ? 'ja' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)
  const setLocale = (next: Locale) => {
    localStorage.setItem(STORAGE_KEY, next)
    setLocaleState(next)
  }
  const t = (key: string) => DICTIONARIES[locale][key] ?? DICTIONARIES.en[key] ?? key
  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>{children}</I18nContext.Provider>
  )
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used within I18nProvider')
  return value
}
