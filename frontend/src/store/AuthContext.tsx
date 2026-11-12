/** Auth state (the signed-in user and scopes). Authorization checks go through hasScope. */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { clearSessionDrafts } from '../hooks/useSessionDraft'
import { ApiError, api } from '../services/api'
import { currentOutage, subscribeOutage } from '../services/maintenance'
import { subscribeSessionEnded } from '../services/sessionEnded'
import { exchangeSsoTicket, startSsoLogout } from '../services/sso'
import { clearSilentSsoMarks, markSignedOut } from '../services/silentSso'
import { rememberTenant, rememberedTenant } from '../services/tenantEntrance'
import { assertPasskey, type PasskeyChallenge } from '../services/webauthn'

export interface Me {
  user_id: number
  email: string
  username: string
  /** Currently effective scopes (permissions after narrowing by the active role). */
  scopes: string[]
  /** All granted roles = the roles one can switch to (ADR-0078 §1). */
  roles: string[]
  /** null means "all roles" (the union of held permissions). */
  active_role: string | null
  /**
   * Whether the user has a password as a way in (ADR-0076 §6).
   * false = a user who can only sign in via SSO. The UI does not offer a password change.
   */
  has_password: boolean
  /**
   * Whether sign-out goes through to the IdP (a server setting; false by default. ADR-0077 §2).
   * It is carried on `/me`, so signing out needs no extra request.
   */
  rp_logout_enabled: boolean
  /** Linked to the IdP. Name and email are edited at the IdP (ADR-0094). */
  profile_managed_by_idp?: boolean
  /** While true, only the two-factor enrollment screen is usable (ADR-0093). */
  two_factor_setup_required?: boolean
}

/** Login succeeded, plus the access token lifetime (the token itself is in a cookie). */
interface SessionInfo {
  expires_in: number
}

interface AuthValue {
  user: Me | null
  loading: boolean
  /**
   * The server is unreachable (5xx or a network failure), e.g. while a new version is rolling out.
   * ⚠ **Do not set user to null here** — the user did not sign out. Sending them to the login
   * screen would strand them, even after the server is back, on a screen with no IdP entrance.
   * Re-ask automatically until the connection returns.
   */
  unreachable: boolean
  /** Accounts with two-factor auth need totpCode (without it the result is totp_required). */
  login: (email: string, password: string, totpCode?: string, tenant?: string) => Promise<void>
  loginWithPasskey: () => Promise<void>
  /**
   * Exchange the SSO ticket for tokens and become signed in (ADR-0077 §1).
   * Returns the return-to location (the screen that started SSO).
   */
  completeSsoLogin: (ticket: string) => Promise<string>
  /** Sign out. Whether it reaches the IdP depends on the server setting (off by default). */
  logout: () => Promise<void>
  refreshMe: () => Promise<void>
  /** Switch the active role (null returns to all roles. ADR-0078 §1). */
  switchRole: (role: string | null) => Promise<void>
  hasScope: (...codes: string[]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

const SERVER_ERROR = 500
/** Interval for re-asking while the server is unreachable */
export const RECONNECT_INTERVAL_MS = 5000

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [unreachable, setUnreachable] = useState(false)

  /**
   * Signed-in status is **decided by whether ``/api/auth/me`` succeeds** (ADR-0076 §4).
   *
   * The token lives in an httpOnly cookie that JavaScript cannot see, so no local value can
   * decide it. Instead of guessing whether a cookie exists, ask whether a request actually
   * gets through.
   */
  const refreshMe = useCallback(async () => {
    try {
      setUser(await api.get<Me>('/api/auth/me'))
      setUnreachable(false)
    } catch (e) {
      // 4xx (401 etc.) means the server answered "not signed in". Anything else did not get through
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
      // Do not re-ask while the front gate is closed; the maintenance screen re-checks
      // (ADR-0080 §10)
      if (currentOutage()) return
      void refreshMe()
    }, RECONNECT_INTERVAL_MS)
    return () => {
      window.clearInterval(timer)
    }
  }, [unreachable, refreshMe])

  // The session could not be continued (ADR-0104). The UI moves to the login screen (the
  // destination and drafts are kept)
  useEffect(
    () =>
      subscribeSessionEnded(() => {
        setUser(null)
      }),
    [],
  )

  // Re-ask as soon as the front gate opens (a page opened while it was closed does not yet know
  // who the user is)
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
      // The entrance tenant (`/t/<slug>/login`. ADR-0079 §4)
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
   * Switching reissues the token (the server narrows the scopes again).
   * /me is re-fetched after the new token is in place, so the scopes shown on screen never
   * disagree with the scopes of the token sent from now on.
   */
  const switchRole = async (role: string | null) => {
    await api.post<SessionInfo>('/api/auth/switch-role', { role })
    await refreshMe()
  }

  /**
   * Sign out.
   *
   * **The app session is always ended.** Whether it goes through to the IdP is decided by the
   * server setting (`OIDC_RP_LOGOUT_ENABLED`; disabled by default). That decision already
   * arrives on `/me`, so **signing out needs no extra request**.
   *
   * ⚠ **Read the destination before `setUser(null)`.** Read afterwards, `user` is already null
   * and the IdP is never reached even when enabled.
   *
   * ⚠ **Drop local state without waiting for the round trip.** If `setUser(null)` comes after
   * `POST /logout`, then on a slow or broken connection **pressing the button changes nothing**
   * (it does not look signed out and invites pressing again). Clearing local copies does not
   * need the round trip to succeed — dropping the cookie is the server's job anyway.
   *
   * ⚠ **Wait for `POST /logout` to finish before sending the user to the IdP.** That is a page
   * navigation; starting it without waiting can abort the cookie-dropping round trip and leave
   * **only the app side still signed in**. When disabled, there is no navigation, as before.
   */
  const logout = async () => {
    const toIdp = user?.rp_logout_enabled ?? false
    setUser(null)
    // The IdP SSO session stays by default, so opening the login screen must not sign back in
    // without a click (ADR-0077 §9)
    markSignedOut()
    clearSessionDrafts()
    // The server drops the cookie (it is httpOnly, so it cannot be removed from here).
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
