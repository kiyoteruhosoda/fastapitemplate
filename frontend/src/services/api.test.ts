/** The API client's error-code conversion and how it sends the CSRF token. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, errorMessageKey } from './api'
import { currentOutage, reportOutage, resetOutageForTests } from './maintenance'
import { subscribeSessionEnded } from './sessionEnded'

const { renewInFrame } = vi.hoisted(() => ({ renewInFrame: vi.fn() }))
vi.mock('./silentRenewal', () => ({
  renewInFrame,
  oneAtATime: <T>(task: () => Promise<T>) => task(),
}))

describe('errorMessageKey', () => {
  it('converts an ApiError code to an i18n key', () => {
    expect(errorMessageKey(new ApiError(401, 'invalid_token'))).toBe('error.invalid_token')
  })

  it('rounds non-API exceptions to unknown_error', () => {
    expect(errorMessageKey(new Error('boom'))).toBe('error.unknown_error')
  })

  it('does not crash on non-exception values', () => {
    expect(errorMessageKey(undefined)).toBe('error.unknown_error')
    expect(errorMessageKey('invalid_token')).toBe('error.unknown_error')
  })
})

/**
 * Holds no tokens (ADR-0076 §4). All this layer cares about is sending cookies and putting the
 * CSRF double-submit token on mutating requests.
 */
describe('request construction', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    document.cookie = 'csrf_token=the-token'
    fetchMock.mockReset()
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: () => Promise.resolve({}) })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    document.cookie = 'csrf_token=; max-age=0'
  })

  function initOf(): RequestInit {
    return fetchMock.mock.calls[0]?.[1] as RequestInit
  }

  it('sends cookies (the token travels in a cookie)', async () => {
    await api.get('/api/auth/me')
    expect(initOf().credentials).toBe('same-origin')
  })

  it('does not put the CSRF token on reads', async () => {
    await api.get('/api/auth/me')
    expect(initOf().headers).not.toHaveProperty('X-CSRF-Token')
  })

  it('puts the CSRF token read from the cookie on mutating requests', async () => {
    await api.post('/api/items', { name: 'x' })
    expect((initOf().headers as Record<string, string>)['X-CSRF-Token']).toBe('the-token')
  })

  it('adds no Authorization header (no token is held locally)', async () => {
    await api.post('/api/items', { name: 'x' })
    expect(initOf().headers).not.toHaveProperty('Authorization')
  })
})

/**
 * After a 401, continue the session once (ADR-0104). Password/passkey sessions use the refresh
 * endpoint; SSO sessions ask the IdP in a hidden frame.
 */
describe('continuing the session', () => {
  const expired = { detail: { error: 'invalid_token', reason: 'token_expired' } }

  function json(status: number, body: unknown = {}): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  beforeEach(() => {
    renewInFrame.mockReset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests that got 401 at the same time wait on one refresh', async () => {
    let refreshed = false
    const fetchMock = vi.fn((path: string) => {
      if (path === '/api/auth/refresh') {
        refreshed = true
        return Promise.resolve(json(200))
      }
      return Promise.resolve(refreshed ? json(200) : json(401, expired))
    })
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([api.get('/api/a'), api.get('/api/b')])

    const refreshes = fetchMock.mock.calls.filter(([path]) => path === '/api/auth/refresh')
    expect(refreshes).toHaveLength(1)
    expect(renewInFrame).not.toHaveBeenCalled()
  })

  it('without a refresh token (SSO), continues via the IdP in a hidden frame', async () => {
    let renewed = false
    renewInFrame.mockImplementation(() => {
      renewed = true
      return Promise.resolve('renewed')
    })
    const fetchMock = vi.fn((path: string) => {
      if (path === '/api/auth/refresh')
        return Promise.resolve(json(401, { detail: { error: 'invalid_token' } }))
      return Promise.resolve(renewed ? json(200, { ok: 1 }) : json(401, expired))
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.get('/api/items')).resolves.toEqual({ ok: 1 })
    expect(renewInFrame).toHaveBeenCalledTimes(1)
  })

  it('when the IdP declines, reports the session ended and throws', async () => {
    renewInFrame.mockResolvedValue('declined')
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(401, expired))),
    )
    const ended = vi.fn()
    const stop = subscribeSessionEnded(ended)

    await expect(api.get('/api/items')).rejects.toMatchObject({ status: 401 })
    expect(ended).toHaveBeenCalledTimes(1)
    // This tab no longer tries on the sign-in screen (ADR-0077 §10)
    expect(window.sessionStorage.getItem('ssoSilentTried')).toBe('1')
    stop()
  })

  it('does not ask the IdP after signing out', async () => {
    window.localStorage.setItem('ssoSignedOut', '1')
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(json(401, expired))),
    )

    await expect(api.get('/api/items')).rejects.toMatchObject({ status: 401 })
    expect(renewInFrame).not.toHaveBeenCalled()
  })

  it('does not continue on an entry-point 401 (wrong password)', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(json(401, { detail: { error: 'invalid_credentials' } })),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.post('/api/auth/login', {})).rejects.toMatchObject({
      code: 'invalid_credentials',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(renewInFrame).not.toHaveBeenCalled()
  })
})

describe('503 from a closed front tier', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    resetOutageForTests()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetOutageForTests()
  })

  function respond(status: number, body: unknown) {
    fetchMock.mockResolvedValueOnce({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    })
  }

  it('reports to the maintenance screen and throws service_unavailable', async () => {
    respond(503, { error: 'service_unavailable', reason: 'maintenance', message: 'Test.' })

    await expect(api.get('/api/items')).rejects.toMatchObject({
      status: 503,
      code: 'service_unavailable',
    })
    expect(currentOutage()).toMatchObject({ reason: 'maintenance', message: 'Test.' })
  })

  it("does not treat the app's own 503 as maintenance", async () => {
    respond(503, { detail: { error: 'restart_request_failed' } })

    await expect(api.get('/api/items')).rejects.toMatchObject({ code: 'restart_request_failed' })
    expect(currentOutage()).toBeNull()
  })

  it('clears the closed state once a response comes back', async () => {
    reportOutage({ reason: 'stopped', title: null, body: null, message: null, until: null })
    respond(200, {})

    await api.get('/api/items')

    expect(currentOutage()).toBeNull()
  })
})
