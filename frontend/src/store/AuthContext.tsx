/** 認証状態（ログイン中ユーザーと scope）。認可判定は hasScope で行う。 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { ApiError, api } from '../services/api'
import { currentOutage, subscribeOutage } from '../services/maintenance'
import { exchangeSsoTicket, startSsoLogout } from '../services/sso'
import { clearSilentSsoMarks, markSignedOut } from '../services/silentSso'
import { rememberTenant, rememberedTenant } from '../services/tenantEntrance'
import { assertPasskey, type PasskeyChallenge } from '../services/webauthn'

export interface Me {
  user_id: number
  email: string
  username: string
  /** いま有効な scope（アクティブロールで絞り込まれた後の権限）。 */
  scopes: string[]
  /** 付与されている全ロール = 切り替えられる先（ADR-0078 §1）。 */
  roles: string[]
  /** null は「すべてのロール」（保有権限の和集合）。 */
  active_role: string | null
  /**
   * パスワードという入り口を持っているか（ADR-0076 §6）。
   * 偽 = SSO でしか入れない利用者。画面はパスワード変更の導線を出さない。
   */
  has_password: boolean
  /**
   * サインアウトを IdP まで通すか（サーバーの設定。既定は偽。ADR-0077 §2）。
   * `/me` に載せてあるので、サインアウトのために問い合わせを増やさない。
   */
  rp_logout_enabled: boolean
}

/** ログインが成立したことと、アクセストークンの寿命（トークン本体は Cookie）。 */
interface SessionInfo {
  expires_in: number
}

interface AuthValue {
  user: Me | null
  loading: boolean
  /**
   * サーバーに届かない（5xx・通信の失敗）。新しい版を配っている最中など。
   * ⚠ **このとき user を null にしない**——ログアウトしたのではないので、ログイン画面へ
   * 送ると、戻ってきたあとも IdP の入口の無い画面に取り残される。つながるまで自動で聞き直す。
   */
  unreachable: boolean
  /** 二要素認証が有効なアカウントでは totpCode が必要（未指定なら totp_required）。 */
  login: (email: string, password: string, totpCode?: string, tenant?: string) => Promise<void>
  loginWithPasskey: () => Promise<void>
  /**
   * SSO の引き換え券をトークンへ換えてログイン状態にする（ADR-0077 §1）。
   * 戻り先（SSO を始めた画面）を返す。
   */
  completeSsoLogin: (ticket: string) => Promise<string>
  /** サインアウト。IdP まで通すかはサーバーの設定次第（既定は通さない）。 */
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
  /** アクティブロールを切り替える（null ですべてのロールへ戻す。ADR-0078 §1）。 */
  switchRole: (role: string | null) => Promise<void>
  hasScope: (...codes: string[]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

const SERVER_ERROR = 500
/** サーバーに届かないとき、聞き直す間隔 */
export const RECONNECT_INTERVAL_MS = 5000

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [unreachable, setUnreachable] = useState(false)

  /**
   * ログイン済みかは **``/api/auth/me`` の成否で決める**（ADR-0076 §4）。
   *
   * トークンは httpOnly Cookie にあり JavaScript からは見えないので、手元の値を
   * 見て判断することはできない。「Cookie があるか」を推し量る代わりに、実際に
   * 通るかを聞く。
   */
  const refreshMe = useCallback(async () => {
    try {
      setUser(await api.get<Me>('/api/auth/me'))
      setUnreachable(false)
    } catch (e) {
      // 4xx（401 など）はサーバーが「ログインしていない」と答えたもの。それ以外は届いていない
      if (e instanceof ApiError && e.status < SERVER_ERROR) {
        setUser(null)
        setUnreachable(false)
      } else {
        setUnreachable(true)
      }
    }
  }, [])

  useEffect(() => {
    if (!unreachable) return
    const timer = window.setInterval(() => {
      // 前段が閉じている間は聞き直さない。確かめ直すのはメンテナンスの画面（ADR-0080 §10）
      if (currentOutage()) return
      void refreshMe()
    }, RECONNECT_INTERVAL_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [unreachable, refreshMe])

  // 前段が開いたら、すぐに聞き直す（閉じている間に開いた画面は、まだ誰かを知らない）
  useEffect(
    () =>
      subscribeOutage(() => {
        if (!currentOutage()) void refreshMe()
      }),
    [refreshMe],
  )

  useEffect(() => {
    void refreshMe().finally(() => {
      setLoading(false)
    })
  }, [refreshMe])

  const login = async (email: string, password: string, totpCode?: string, tenant?: string) => {
    await api.post<SessionInfo>('/api/auth/login', {
      email,
      password,
      totp_code: totpCode || null,
      // 入口のテナント（`/t/<slug>/login`。ADR-0079 §4）
      tenant: tenant ?? null,
    })
    rememberTenant(tenant)
    clearSilentSsoMarks()
    await refreshMe()
  }

  const loginWithPasskey = async () => {
    const challenge = await api.post<PasskeyChallenge>('/api/auth/passkey/challenge')
    const credential = await assertPasskey(challenge.public_key)
    await api.post<SessionInfo>('/api/auth/passkey/login', {
      challenge_id: challenge.challenge_id,
      credential,
    })
    clearSilentSsoMarks()
    await refreshMe()
  }

  const completeSsoLogin = async (ticket: string) => {
    const session = await exchangeSsoTicket(ticket)
    clearSilentSsoMarks()
    await refreshMe()
    return session.redirect_to
  }

  /**
   * 切り替えはトークンの再発行で行う（サーバー側が scope を絞り直す）。
   * 新しいトークンに差し替えてから /me を引き直すので、画面に出る scope と
   * これから送るトークンの scope が食い違わない。
   */
  const switchRole = async (role: string | null) => {
    await api.post<SessionInfo>('/api/auth/switch-role', { role })
    await refreshMe()
  }

  /**
   * サインアウト。
   *
   * **アプリのセッションは必ず終わらせる。** IdP まで通すかどうかは
   * サーバーの設定（`OIDC_RP_LOGOUT_ENABLED`。既定は無効）で決まる。判断は
   * `/me` に載って届いているので、**サインアウトのために問い合わせを増やさない**。
   *
   * ⚠ **行き先は `setUser(null)` の前に読む。** あとで読むと `user` は既に null で、
   * 有効な構成でも IdP へ行かなくなる。
   *
   * ⚠ **手元の状態は往復を待たずに落とす。** `setUser(null)` を `POST /logout` の
   * あとに置くと、回線が遅い・切れているときに**押しても画面が変わらない**
   * （サインアウト済みに見えず、押し直しを誘う）。手元の控えを消すのに往復の
   * 成否は要らない——Cookie を落とすのはどのみちサーバー側。
   *
   * ⚠ **IdP へ送り出す前に `POST /logout` の完了を待つ。** 送り出しは画面遷移で、
   * 待たずに始めると Cookie を落とす往復が中断され、**アプリ側だけ入ったまま**に
   * なりうる。無効なときは従来どおり画面遷移しない。
   */
  const logout = async () => {
    const toIdp = user?.rp_logout_enabled ?? false
    setUser(null)
    // IdP の SSO は既定で残るので、ログイン画面を開いてもボタンを押さずに入り直さない（ADR-0077 §9）
    markSignedOut()
    // Cookie を落とすのはサーバー側（httpOnly なのでこちらからは消せない）。
    await api.post('/api/auth/logout').catch(() => undefined)
    if (toIdp) startSsoLogout(rememberedTenant())
  }

  const hasScope = (...codes: string[]) =>
    user !== null && codes.every((code) => user.scopes.includes(code))

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        unreachable,
        login,
        loginWithPasskey,
        completeSsoLogin,
        logout,
        refreshMe,
        switchRole,
        hasScope,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
