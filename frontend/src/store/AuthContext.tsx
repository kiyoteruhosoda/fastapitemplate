/** 認証状態（ログイン中ユーザーと scope）。認可判定は hasScope で行う。 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { api, clearTokens, hasTokens, setTokens } from '../services/api'
import { assertPasskey, type PasskeyChallenge } from '../services/webauthn'

export interface Me {
  user_id: number
  email: string
  username: string
  scopes: string[]
}

interface TokenPair {
  access_token: string
  refresh_token: string
}

interface AuthValue {
  user: Me | null
  loading: boolean
  /** 二要素認証が有効なアカウントでは totpCode が必要（未指定なら totp_required）。 */
  login: (email: string, password: string, totpCode?: string) => Promise<void>
  loginWithPasskey: () => Promise<void>
  logout: () => void
  refreshMe: () => Promise<void>
  hasScope: (...codes: string[]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshMe = useCallback(async () => {
    if (!hasTokens()) {
      setUser(null)
      return
    }
    try {
      setUser(await api.get<Me>('/api/auth/me'))
    } catch {
      clearTokens()
      setUser(null)
    }
  }, [])

  useEffect(() => {
    void refreshMe().finally(() => {
      setLoading(false)
    })
  }, [refreshMe])

  const login = async (email: string, password: string, totpCode?: string) => {
    const pair = await api.post<TokenPair>('/api/auth/login', {
      email,
      password,
      totp_code: totpCode || null,
    })
    setTokens(pair.access_token, pair.refresh_token)
    await refreshMe()
  }

  const loginWithPasskey = async () => {
    const challenge = await api.post<PasskeyChallenge>('/api/auth/passkey/challenge')
    const credential = await assertPasskey(challenge.public_key)
    const pair = await api.post<TokenPair>('/api/auth/passkey/login', {
      challenge_id: challenge.challenge_id,
      credential,
    })
    setTokens(pair.access_token, pair.refresh_token)
    await refreshMe()
  }

  const logout = () => {
    void api.post('/api/auth/logout').catch(() => undefined)
    clearTokens()
    setUser(null)
  }

  const hasScope = (...codes: string[]) =>
    user !== null && codes.every((code) => user.scopes.includes(code))

  return (
    <AuthContext.Provider
      value={{ user, loading, login, loginWithPasskey, logout, refreshMe, hasScope }}
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
