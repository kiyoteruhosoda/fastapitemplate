/** 認証状態（ログイン中ユーザーと scope）。認可判定は hasScope で行う。 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

import { api, clearTokens, hasTokens, setTokens } from '../services/api'

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
  login: (email: string, password: string) => Promise<void>
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
    refreshMe().finally(() => setLoading(false))
  }, [refreshMe])

  const login = async (email: string, password: string) => {
    const pair = await api.post<TokenPair>('/api/auth/login', { email, password })
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
    <AuthContext.Provider value={{ user, loading, login, logout, refreshMe, hasScope }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
