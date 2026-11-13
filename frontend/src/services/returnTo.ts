/**
 * Keep the destination across the sign-in round trip (ADR-0077 §8).
 *
 * Opening a deep link (`/items?q=…` etc.) while signed out sends the user to the sign-in screen.
 * Sending them without the destination lands them on the landing page (`/`) after sign-in, and
 * **they can never get back to the screen they were opening**. Carry the query too, not just the
 * path.
 *
 * WARNING: **Never return to an external URL.** The authoritative validation is server-side
 * (`RedirectTarget.parse`); this only narrows to the same shape before passing it on.
 */
import { loginPathOf, rememberedTenant } from './tenantEntrance'

/** Query name used by the sign-in screen and the SSO entry point (same spelling on both sides). */
export const REDIRECT_TO_PARAM = 'redirect_to'

/** Where to return when there is no destination (or it points outside). */
const LANDING = '/'

/**
 * Length limit the server accepts (`redirect_to` of `/api/auth/sso/login`, and the round-trip
 * record column).
 * A longer value would stop the entry point with 422, so fall back to the landing page.
 */
const MAX_LENGTH = 255

/**
 * Allow only absolute paths within this site. WARNING: same rule as the server; never loosen only
 * one side.
 */
export function sanitizeRedirectTo(candidate: string | null | undefined): string {
  if (!candidate) return LANDING
  if (!candidate.startsWith('/')) return LANDING
  // `//evil.example` is a protocol-relative URL; browsers resolve it as external.
  if (candidate.startsWith('//')) return LANDING
  // Some browsers resolve `/\evil.example` as external.
  if (candidate.startsWith('/\\')) return LANDING
  if (candidate.includes('\r') || candidate.includes('\n')) return LANDING
  if (candidate.length > MAX_LENGTH) return LANDING
  return candidate
}

/**
 * Sign-in screen URL to send a signed-out user to.
 *
 * Coming from the landing page (`/`) adds no destination (landing after sign-in is the default).
 */
export function signInPathFor(location: { pathname: string; search?: string }): string {
  const here = sanitizeRedirectTo(`${location.pathname}${location.search ?? ''}`)
  // Return to the entry point (tenant) used last time (ADR-0079 §4)
  const login = loginPathOf(rememberedTenant())
  if (here === LANDING) return login
  return `${login}?${REDIRECT_TO_PARAM}=${encodeURIComponent(here)}`
}
