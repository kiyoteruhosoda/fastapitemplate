/** 認証状態（ログイン中ユーザーと scope）。認可判定は hasScope で行う。 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { api } from '../services/api'
import { exchangeSsoTicket } from '../services/sso'
import { assertPasskey, type PasskeyChallenge } from '../services/webauthn'

export interface Me {
  user_id: number
  email: string
  username: string
  /** いま有効な scope（アクティブロールで絞り込まれた後の権限）。 */
  scopes: string[]
  /** 付与されている全ロール = 切り替えられる先（ADR-0017）。 */
  roles: string[]
  /** null は「すべてのロール」（保有権限の和集合）。 */
  active_role: string | null
}

/** ログインが成立したことと、アクセストークンの寿命（トークン本体は Cookie）。 */
interface SessionInfo {
  expires_in: number
}

interface AuthValue {
  user: Me | null
  loading: boolean
  /** 二要素認証が有効なアカウントでは totpCode が必要（未指定なら totp_required）。 */
  login: (email: string, password: string, totpCode?: string) => Promise<void>
  loginWithPasskey: () => Promise<void>
  /**
   * SSO の引き換え券をトークンへ換えてログイン状態にする（ADR-0025）。
   * 戻り先（SSO を始めた画面）を返す。
   */
  completeSsoLogin: (ticket: string) => Promise<string>
  logout: () => void
  refreshMe: () => Promise<void>
  /** アクティブロールを切り替える（null ですべてのロールへ戻す。ADR-0017）。 */
  switchRole: (role: string | null) => Promise<void>
  hasScope: (...codes: string[]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  /**
   * ログイン済みかは **``/api/auth/me`` の成否で決める**（ADR-0028）。
   *
   * トークンは httpOnly Cookie にあり JavaScript からは見えないので、手元の値を
   * 見て判断することはできない。「Cookie があるか」を推し量る代わりに、実際に
   * 通るかを聞く。
   */
  const refreshMe = useCallback(async () => {
    try {
      setUser(await api.get<Me>('/api/auth/me'))
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    void refreshMe().finally(() => {
      setLoading(false)
    })
  }, [refreshMe])

  const login = async (email: string, password: string, totpCode?: string) => {
    await api.post<SessionInfo>('/api/auth/login', {
      email,
      password,
      totp_code: totpCode || null,
    })
    await refreshMe()
  }

  const loginWithPasskey = async () => {
    const challenge = await api.post<PasskeyChallenge>('/api/auth/passkey/challenge')
    const credential = await assertPasskey(challenge.public_key)
    await api.post<SessionInfo>('/api/auth/passkey/login', {
      challenge_id: challenge.challenge_id,
      credential,
    })
    await refreshMe()
  }

  const completeSsoLogin = async (ticket: string) => {
    const session = await exchangeSsoTicket(ticket)
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

  const logout = () => {
    // Cookie を落とすのはサーバー側（httpOnly なのでこちらからは消せない）。
    void api.post('/api/auth/logout').catch(() => undefined)
    setUser(null)
  }

  const hasScope = (...codes: string[]) =>
    user !== null && codes.every((code) => user.scopes.includes(code))

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
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
