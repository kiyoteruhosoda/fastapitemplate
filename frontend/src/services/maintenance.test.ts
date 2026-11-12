/**
 * Receiving the front tier (edge) saying it is closed (ADR-0080 §10).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  checkService,
  currentOutage,
  outageFrom,
  reportOutage,
  resetOutageForTests,
  watchLazyLoadFailures,
} from './maintenance'

const MAINTENANCE = {
  error: 'service_unavailable',
  reason: 'maintenance',
  until: '2026-10-28T19:30:00Z',
  message: 'Test.',
  title: 'T',
  body: 'B',
}

/** The shape edge returned before title/body were added (before task #663). */
const OLD_MAINTENANCE = {
  error: 'service_unavailable',
  reason: 'maintenance',
  until: '2026-10-28T19:30:00Z',
  message: 'Test.',
}

function respond(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

describe('outageFrom', () => {
  it('reads the maintenance declaration text', () => {
    expect(outageFrom(503, MAINTENANCE)).toEqual({
      reason: 'maintenance',
      title: 'T',
      body: 'B',
      message: 'Test.',
      until: '2026-10-28T19:30:00Z',
    })
  })

  it('reads the old edge shape (no title/body) as closed', () => {
    expect(outageFrom(503, OLD_MAINTENANCE)).toMatchObject({
      reason: 'maintenance',
      title: null,
      body: null,
      message: 'Test.',
    })
  })

  it('is stopped when only the upstream is down', () => {
    expect(outageFrom(503, { error: 'service_unavailable', reason: 'stopped', host: 'x' })).toEqual(
      { reason: 'stopped', title: null, body: null, message: null, until: null },
    )
  })

  it("does not treat the app's own error shape or non-503 as closed", () => {
    expect(outageFrom(503, { detail: { error: 'service_unavailable' } })).toBeNull()
    expect(outageFrom(503, null)).toBeNull()
    expect(outageFrom(500, MAINTENANCE)).toBeNull()
    expect(outageFrom(503, { error: 'service_unavailable', reason: 'other' })).toBeNull()
  })
})

describe('checkService', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    resetOutageForTests()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sets the closed state on a 503 declaration and clears it once through', async () => {
    fetchMock.mockReturnValueOnce(respond(503, MAINTENANCE))
    await expect(checkService()).resolves.toBe('closed')
    expect(currentOutage()?.title).toBe('T')

    fetchMock.mockReturnValueOnce(respond(200, {}))
    await expect(checkService()).resolves.toBe('open')
    expect(currentOutage()).toBeNull()
  })

  it('leaves the state unchanged when unreachable', async () => {
    reportOutage({ reason: 'maintenance', title: null, body: null, message: null, until: null })
    fetchMock.mockRejectedValueOnce(new Error('offline'))

    await expect(checkService()).resolves.toBe('unknown')
    expect(currentOutage()).not.toBeNull()
  })

  it('does not use a cached answer', async () => {
    fetchMock.mockReturnValueOnce(respond(200, {}))
    await checkService()
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).cache).toBe('no-store')
  })
})

/** Lazily loaded chunk failures (AC6). */
describe('watchLazyLoadFailures', () => {
  const fetchMock = vi.fn()
  const reload = vi.fn()
  let stop: () => void = () => undefined

  beforeEach(() => {
    resetOutageForTests()
    fetchMock.mockReset()
    reload.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    stop = watchLazyLoadFailures(window, reload)
  })

  afterEach(() => {
    stop()
    vi.unstubAllGlobals()
  })

  function failLazyLoad(): Event {
    const event = new Event('vite:preloadError', { cancelable: true })
    window.dispatchEvent(event)
    return event
  }

  it('shows the maintenance screen if closed and reloads once open', async () => {
    fetchMock.mockReturnValueOnce(respond(503, MAINTENANCE))
    failLazyLoad()
    await vi.waitFor(() => {
      expect(currentOutage()?.reason).toBe('maintenance')
    })

    fetchMock.mockReturnValueOnce(respond(200, {}))
    await checkService()
    expect(currentOutage()).toBeNull()
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('does nothing on a plain failure (the error is still thrown)', async () => {
    fetchMock.mockReturnValueOnce(respond(200, {}))
    const event = failLazyLoad()
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    expect(event.defaultPrevented).toBe(false)
    expect(currentOutage()).toBeNull()
    expect(reload).not.toHaveBeenCalled()
  })

  it("does not treat the app's own 503 as maintenance", async () => {
    fetchMock.mockReturnValueOnce(respond(503, { detail: { error: 'x' } }))
    failLazyLoad()
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    expect(currentOutage()).toBeNull()
  })
})
