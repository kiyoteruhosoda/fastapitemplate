/**
 * 画面の初期設定（言語・テーマ）。
 *
 * 管理画面で運用者が決めた既定値をサーバーから受け取り、利用者がまだ何も
 * 選んでいないときの初期値として使う。ログイン前の画面でも必要なため、
 * 認証前に一度だけ取得する（`main.tsx`）。
 */

export interface UiSettings {
  languages: string[]
  default_locale: string
  default_theme: string
}

/** サーバーへ到達できない場合でも画面は出す。そのときの保険。 */
export const FALLBACK_UI_SETTINGS: UiSettings = {
  languages: ['en', 'ja'],
  default_locale: 'en',
  default_theme: 'system',
}

export async function loadUiSettings(): Promise<UiSettings> {
  try {
    const response = await fetch('/api/ui/settings')
    if (!response.ok) return FALLBACK_UI_SETTINGS
    return (await response.json()) as UiSettings
  } catch {
    return FALLBACK_UI_SETTINGS
  }
}
