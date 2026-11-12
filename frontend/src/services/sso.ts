/**
 * Sign-in via an external IdP (OIDC) (ADR-0077 §1).
 *
 * Starting is done by browser navigation (fetch can't show the IdP's sign-in page).
 * On return from the IdP the URL carries no token; instead it carries a one-time exchange
 * ticket. `exchangeSsoTicket` exchanges it for tokens.
 */
import { api } from './api'

export interface SsoProvider {
  enabled: boolean
  /** Name shown on the sign-in button (what the IdP is called). */
  display_name: string
  /**
   * Whether the password/passkey entry points are open (ADR-0076 §3, decision 2).
   * If false, the sign-in screen shows neither the password field nor the passkey button.
   */
  local_login_enabled: boolean
  /**
   * Whether sign-out goes through to the IdP (default false). Only when true, after the app's
   * sign-out completes, `startSsoLogout` sends the browser to the IdP.
   */
  rp_logout_enabled: boolean
}

export interface SsoSession {
  expires_in: number
  /** Screen where SSO started (an in-app path). */
  redirect_to: string
}

/** Ask whether SSO is configured (callable unauthenticated). */
export function fetchSsoProvider(tenant?: string): Promise<SsoProvider> {
  const query = tenant ? `?${new URLSearchParams({ tenant }).toString()}` : ''
  return api.get<SsoProvider>(`/api/auth/sso/provider${query}`)
}

/**
 * Send the browser to the IdP. Returns to `redirectTo` (only in-app paths are valid).
 * With `silent`, add `prompt=none` (the attempt when the sign-in screen opens; ADR-0077 §9).
 *
 * Use `replace`, not `assign`. Leaving the sign-in screen in history would make "Back" after
 * signing in return to the sign-in screen.
 */
export function startSsoLogin(
  redirectTo: string,
  tenant?: string,
  options: { silent?: boolean } = {},
): void {
  const query = new URLSearchParams({ redirect_to: redirectTo })
  // The destination is the tenant's IdP (ADR-0079 §4)
  if (tenant) query.set('tenant', tenant)
  // Try without letting the IdP show a screen (ADR-0077 §9; services/silentSso.ts)
  if (options.silent) query.set('prompt', 'none')
  window.location.replace(`/api/auth/sso/login?${query.toString()}`)
}

/**
 * Carry sign-out through to the IdP (RP-Initiated Logout).
 *
 * Like `startSsoLogin`, this only works via **navigation**. Only the IdP itself can drop the
 * IdP's cookies, so fetch can't reach them.
 *
 * Use `replace`. Leaving the signed-out screen in history would let "Back" return to it,
 * making it unclear whether the user signed out.
 */
export function startSsoLogout(tenant?: string): void {
  const query = tenant ? `?${new URLSearchParams({ tenant }).toString()}` : ''
  window.location.replace(`/api/auth/sso/logout${query}`)
}

/** Exchange the ticket for tokens. */
export function exchangeSsoTicket(ticket: string): Promise<SsoSession> {
  return api.post<SsoSession>('/api/auth/sso/token', { ticket })
}
