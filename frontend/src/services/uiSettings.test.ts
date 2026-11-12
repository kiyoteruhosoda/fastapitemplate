/** Fetching the initial UI settings (including the fallback when the server is unreachable). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { currentOutage, resetOutageForTests } from './maintenance'
import { FALLBACK_UI_SETTINGS, loadUiSettings } from './uiSettings'

function stubFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal('fetch', vi.fn(impl))
}

describe('loadUiSettings', () => {
  beforeEach(() => {
    resetOutageForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("uses the server's response as is", async () => {
    const payload = { languages: ['ja'], default_locale: 'ja', default_theme: 'dark' }
    stubFetch(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    )

    await expect(loadUiSettings()).resolves.toEqual(payload)
  })

  it('falls back to defaults on an error response', async () => {
    stubFetch(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }))

    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
  })

  it('shows the screen with defaults even if the request itself fails', async () => {
    stubFetch(() => Promise.reject(new Error('offline')))

    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
  })

  it('starts on the maintenance screen if the front tier is closed (ADR-0080 §10)', async () => {
    const declared = {
      error: 'service_unavailable',
      reason: 'maintenance',
      until: '2026-10-28T19:30:00Z',
      message: 'Test.',
      title: 'T',
      body: 'B',
    }
    stubFetch(() =>
      Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve(declared) }),
    )

    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
    expect(currentOutage()).toMatchObject({ reason: 'maintenance', until: '2026-10-28T19:30:00Z' })
  })

  it("treats neither the app's own 503 nor an unreadable 503 as maintenance", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ detail: { error: 'service_unavailable' } }),
      }),
    )
    await loadUiSettings()
    expect(currentOutage()).toBeNull()

    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.reject(new SyntaxError('html')),
      }),
    )
    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
    expect(currentOutage()).toBeNull()
  })
})
