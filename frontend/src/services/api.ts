/**
 * API client (fetch wrapper).
 *
 * - **Holds no tokens** (ADR-0076 §4). They travel in httpOnly cookies, so this layer only needs
 *   to send with `credentials: 'same-origin'`.
 * - Mutating requests carry the CSRF double-submit token (the `csrf_token` cookie value).
 * - On 401, continue the session once and retry. Sessions started with a password or passkey
 *   use the refresh endpoint; SSO sessions ask the IdP in a hidden frame (ADR-0104,
 *   `silentRenewal.ts`).
 *   If the session can't be continued, report that it ended (the screen goes to sign-in; drafts
 *   are kept in sessionStorage by `useSessionDraft`).
 * - The backend returns error codes ({"error": "..."}). Converting them to display text is done
 *   by i18n (on the frontend).
 * - A 503 where the front tier (edge) says it is closed is reported to the maintenance screen
 *   (ADR-0080 §10). The exception is still thrown (the caller stops; no toast is shown).
 */
import { currentOutage, outageFrom, reportOutage, reportReopened } from './maintenance'
import { markSilentSsoTried, clearSilentSsoMarks, signedOutHere } from './silentSso'
import { reportSessionEnded } from './sessionEnded'
import { oneAtATime, renewInFrame } from './silentRenewal'

/** CSRF double-submit token. **This is the only cookie JavaScript can read.** */
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const TWO_FACTOR_SETUP_REQUIRED = 'two_factor_setup_required'

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string) {
    super(code)
    this.status = status
    this.code = code
  }
}

/**
 * Convert an exception into an i18n translation key.
 *
 * The backend returns only error codes, so the screen always ends up looking up
 * `error.<code>`. A single entry point so each page doesn't repeat the same branching.
 */
export function errorMessageKey(error: unknown): string {
  return `error.${error instanceof ApiError ? error.code : 'unknown_error'}`
}

/**
 * Read the CSRF token from the cookie.
 *
 * **Re-read it every time.** It changes whenever the session is re-established, so a cached copy
 * would send a stale value after a refresh or a role switch.
 */
function csrfToken(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${CSRF_COOKIE}=([^;]*)`))
  return match?.[1] ? decodeURIComponent(match[1]) : null
}

function extractErrorCode(body: unknown): string {
  if (body && typeof body === 'object') {
    const detail = (body as Record<string, unknown>).detail
    if (detail && typeof detail === 'object') {
      const code = (detail as Record<string, unknown>).error
      if (typeof code === 'string') return code
    }
    if (typeof detail === 'string') return detail
  }
  return 'unknown_error'
}

let refreshing: Promise<boolean> | null = null

/**
 * Continue the session. Tokens travel as cookies both ways, so nothing is carried around here.
 */
function tryRefresh(): Promise<boolean> {
  // Requests that got 401 at the same time wait on a single attempt (ADR-0091)
  refreshing ??= continueSession().finally(() => {
    refreshing = null
  })
  return refreshing
}

async function continueSession(): Promise<boolean> {
  // Password/passkey sessions hold a refresh token (SSO sessions don't, so this returns 401)
  if (await sendRefresh()) return true
  // Don't ask the IdP after signing out (the IdP session persists by default, so it would sign
  // straight back in)
  if (signedOutHere()) return false
  return oneAtATime(async () => {
    // Another tab may have continued the session while we waited (cookies are shared)
    if (await stillSignedIn()) return true
    const result = await renewInFrame()
    if (result === 'renewed') clearSilentSsoMarks()
    // Declined: don't try again in this tab even if the sign-in screen opens (a reload does;
    // ADR-0077 §10)
    else if (result === 'declined') markSilentSsoTried()
    return result === 'renewed'
  })
}

async function sendRefresh(): Promise<boolean> {
  const headers: Record<string, string> = {}
  const csrf = csrfToken()
  if (csrf) headers[CSRF_HEADER] = csrf
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers,
    credentials: 'same-origin',
  })
  return response.ok
}

async function stillSignedIn(): Promise<boolean> {
  const response = await fetch('/api/auth/me', { credentials: 'same-origin' })
  return response.ok
}

/**
 * Whether the 401 means the session expired or is missing. Don't continue on entry-point 401s
 * (wrong password, missing second factor, etc.) — otherwise a mistyped password would query
 * the IdP.
 */
const SESSION_ERRORS = new Set(['authentication_required', 'invalid_token'])

async function meansSessionExpired(response: Response): Promise<boolean> {
  try {
    return SESSION_ERRORS.has(extractErrorCode(await response.clone().json()))
  } catch {
    return false
  }
}

/**
 * Turn a failed response into an exception. A closed front tier or required 2FA setup is reported
 * to the screen here.
 */
async function failureOf(response: Response): Promise<ApiError> {
  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    /* non-JSON response */
  }
  const outage = outageFrom(response.status, payload)
  if (outage) {
    reportOutage(outage)
    return new ApiError(response.status, 'service_unavailable')
  }
  const code = extractErrorCode(payload)
  // Became required mid-use. Reloading /me shows the enrollment screen (ADR-0093)
  if (code === TWO_FACTOR_SETUP_REQUIRED) window.location.reload()
  return new ApiError(response.status, code)
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (UNSAFE_METHODS.has(method)) {
    const csrf = csrfToken()
    if (csrf) headers[CSRF_HEADER] = csrf
  }

  const init: RequestInit = { method, headers, credentials: 'same-origin' }
  if (body !== undefined) init.body = JSON.stringify(body)

  const response = await fetch(path, init)

  if (response.status === 401 && retry && (await meansSessionExpired(response))) {
    if (await tryRefresh()) return request<T>(method, path, body, false)
    reportSessionEnded()
  }
  if (!response.ok) throw await failureOf(response)
  // Got a response = not closed (restore from the maintenance screen if shown)
  if (currentOutage()) reportReopened()
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
