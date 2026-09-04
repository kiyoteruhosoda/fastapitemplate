/**
 * 外部 IdP（OIDC）によるログイン（ADR-0025）。
 *
 * 開始はブラウザの画面遷移で行う（fetch では IdP のログイン画面を出せない）。
 * IdP から戻ってきた時点でトークンは URL に載っておらず、代わりに 1 回限りの
 * 引き換え券が付く。それをトークンへ換えるのが `exchangeSsoTicket`。
 */
import { api } from './api'

export interface SsoProvider {
  enabled: boolean
  /** ログインボタンに出す名前（IdP の呼び名）。 */
  display_name: string
  /**
   * パスワード・パスキーの入口が開いているか（ADR-0026 決定 2）。
   * 偽ならログイン画面はパスワード欄とパスキーのボタンを出さない。
   */
  local_login_enabled: boolean
}

export interface SsoSession {
  access_token: string
  refresh_token: string
  /** SSO を始めた画面（アプリ内の経路）。 */
  redirect_to: string
}

/** SSO が使える構成かを問い合わせる（未認証で呼べる）。 */
export function fetchSsoProvider(): Promise<SsoProvider> {
  return api.get<SsoProvider>('/api/auth/sso/provider')
}

/**
 * IdP へ送り出す。戻り先は `redirectTo`（アプリ内の経路のみ有効）。
 *
 * `assign` ではなく `replace` を使う。ログイン画面を履歴に残すと、ログイン後の
 * 「戻る」でログイン画面へ戻ってしまうため。
 */
export function startSsoLogin(redirectTo: string): void {
  const query = new URLSearchParams({ redirect_to: redirectTo })
  window.location.replace(`/api/auth/sso/login?${query.toString()}`)
}

/** 引き換え券をトークンへ換える。 */
export function exchangeSsoTicket(ticket: string): Promise<SsoSession> {
  return api.post<SsoSession>('/api/auth/sso/token', { ticket })
}
