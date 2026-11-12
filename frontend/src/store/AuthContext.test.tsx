/**
 * Local markers left on sign-in / sign-out, and re-asking while the front gate is closed.
 *
 * - On sign-in, clear the marker of the no-click sign-in attempt (ADR-0077 §9). If it stays,
 *   the next expiry will not try again
 * - On sign-out, set the marker. Without it, the IdP SSO session still exists and the user is
 *   signed straight back in
 * - Remember the entrance tenant used to sign in (ADR-0079 §4), and send the IdP sign-out to
 *   that tenant too
 * - While the front gate is closed, do not re-ask `/me`; re-ask right away once it opens
 *   (ADR-0080 §10)
 */
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiModule from '../services/api'
import { ApiError } from '../services/api'
import { reportOutage, reportReopened, resetOutageForTests } from '../services/maintenance'
import { maySilentSso } from '../services/silentSso'
import { rememberTenant, rememberedTenant } from '../services/tenantEntrance'
import { AuthProvider, RECONNECT_INTERVAL_MS, useAuth, type Me } from './AuthContext'

const { get, post, exchangeSsoTicket, startSsoLogout, assertPasskey } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  exchangeSsoTicket: vi.fn(),
  startSsoLogout: vi.fn(),
  assertPasskey: vi.fn(),
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get, post },
}))
vi.mock('../services/sso', () => ({ exchangeSsoTicket, startSsoLogout }))
vi.mock('../services/webauthn', () => ({ assertPasskey }))

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: [],
  roles: ['owner'],
  active_role: null,
  has_password: true,
  rp_logout_enabled: false,
}

const DECLARED = {
  reason: 'maintenance',
  title: null,
  body: null,
  message: null,
  until: null,
} as const

/** Access the rendered AuthProvider's value from outside. */
function renderAuth(): { current: () => ReturnType<typeof useAuth> } {
  let latest: ReturnType<typeof useAuth> | null = null
  function Probe() {
    latest = useAuth()
    return null
  }
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
  return {
    current: () => {
      if (!latest) throw new Error('AuthProvider has not rendered')
      return latest
    },
  }
}

async function renderSignedOut() {
  get.mockRejectedValue(new ApiError(401, 'not_authenticated'))
  const auth = renderAuth()
  await waitFor(() => {
    expect(auth.current().loading).toBe(false)
  })
  get.mockResolvedValue(ME)
  return auth
}

/** Traces of a previous attempt and a sign-out (either one stops the login screen trying). */
function leaveSilentSsoMarks() {
  window.localStorage.setItem('ssoSignedOut', '1')
  window.sessionStorage.setItem('ssoSilentTried', '1')
  expect(maySilentSso(new URLSearchParams())).toBe(false)
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
    resetOutageForTests()
    post.mockResolvedValue({ expires_in: 300 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('clears the attempt marker after signing in (ADR-0077 §9)', () => {
    it('signed in with a password', async () => {
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      await act(() => auth.current().login('admin@example.com', 'pw'))
      expect(auth.current().user).toEqual(ME)
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('signed in with a passkey', async () => {
      post.mockResolvedValueOnce({ challenge_id: 'c', public_key: {} })
      assertPasskey.mockResolvedValue({ id: 'cred' })
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      await act(() => auth.current().loginWithPasskey())
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('signed in with SSO (returns the return-to path)', async () => {
      exchangeSsoTicket.mockResolvedValue({ expires_in: 300, redirect_to: '/items' })
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      let back = ''
      await act(async () => {
        back = await auth.current().completeSsoLogin('ticket')
      })
      expect(back).toBe('/items')
      expect(maySilentSso(new URLSearchParams())).toBe(true)
    })

    it('keeps the marker when sign-in fails', async () => {
      const auth = await renderSignedOut()
      leaveSilentSsoMarks()
      post.mockRejectedValueOnce(new ApiError(401, 'invalid_credentials'))
      await act(async () => {
        await expect(auth.current().login('admin@example.com', 'wrong')).rejects.toThrow()
      })
      expect(maySilentSso(new URLSearchParams())).toBe(false)
    })
  })

  describe('entrance tenant (ADR-0079 §4)', () => {
    it('sends and remembers the entrance tenant used', async () => {
      const auth = await renderSignedOut()
      await act(() => auth.current().login('boss@acme.example', 'pw', undefined, 'acme'))
      expect(post).toHaveBeenCalledWith('/api/auth/login', {
        email: 'boss@acme.example',
        password: 'pw',
        totp_code: null,
        tenant: 'acme',
      })
      expect(rememberedTenant()).toBe('acme')
    })

    it('forgets the previous tenant after signing in through the shared entrance', async () => {
      rememberTenant('acme')
      const auth = await renderSignedOut()
      await act(() => auth.current().login('admin@example.com', 'pw'))
      expect(post).toHaveBeenCalledWith(
        '/api/auth/login',
        expect.objectContaining({ tenant: null }),
      )
      expect(rememberedTenant()).toBeUndefined()
    })
  })

  describe('sign-out', () => {
    it('sets the marker so the next login screen does not try (IdP sign-out disabled)', async () => {
      get.mockResolvedValue(ME)
      const auth = renderAuth()
      await waitFor(() => {
        expect(auth.current().user).toEqual(ME)
      })
      await act(() => auth.current().logout())
      expect(auth.current().user).toBeNull()
      expect(post).toHaveBeenCalledWith('/api/auth/logout')
      expect(maySilentSso(new URLSearchParams())).toBe(false)
      expect(startSsoLogout).not.toHaveBeenCalled()
    })

    it('with IdP sign-out enabled, sends to the entrance tenant IdP after the app sign-out finishes', async () => {
      rememberTenant('acme')
      get.mockResolvedValue({ ...ME, rp_logout_enabled: true })
      let finishLogout: (value: unknown) => void = () => undefined
      post.mockImplementation((path: string) =>
        path === '/api/auth/logout'
          ? new Promise((resolve) => {
              finishLogout = resolve
            })
          : Promise.resolve({ expires_in: 300 }),
      )
      const auth = renderAuth()
      await waitFor(() => {
        expect(auth.current().user).not.toBeNull()
      })
      let done: Promise<void> = Promise.resolve()
      act(() => {
        done = auth.current().logout()
      })
      expect(startSsoLogout).not.toHaveBeenCalled()
      await act(async () => {
        finishLogout(undefined)
        await done
      })
      expect(startSsoLogout).toHaveBeenCalledWith('acme')
    })
  })

  describe('while the front gate is closed (ADR-0080 §10)', () => {
    it('does not re-ask while unreachable if the gate is closed, and re-asks as soon as it opens', async () => {
      vi.useFakeTimers()
      get.mockRejectedValue(new ApiError(503, 'service_unavailable'))
      const auth = renderAuth()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(auth.current().unreachable).toBe(true)

      act(() => {
        reportOutage(DECLARED)
      })
      get.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS * 3)
      })
      expect(get).not.toHaveBeenCalled()

      get.mockResolvedValue(ME)
      await act(async () => {
        reportReopened()
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(get).toHaveBeenCalledTimes(1)
      expect(auth.current().user).toEqual(ME)
      expect(auth.current().unreachable).toBe(false)
    })

    it('re-asks at intervals while unreachable if the gate is not closed', async () => {
      vi.useFakeTimers()
      get.mockRejectedValue(new ApiError(502, 'bad_gateway'))
      const auth = renderAuth()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0)
      })
      expect(auth.current().unreachable).toBe(true)
      get.mockClear()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(RECONNECT_INTERVAL_MS)
      })
      expect(get).toHaveBeenCalledTimes(1)
    })
  })
})
