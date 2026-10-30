/** 画面初期設定の取得（サーバーへ到達できない場合の保険を含む）。 */
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

  it('サーバーの応答をそのまま使う', async () => {
    const payload = { languages: ['ja'], default_locale: 'ja', default_theme: 'dark' }
    stubFetch(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    )

    await expect(loadUiSettings()).resolves.toEqual(payload)
  })

  it('エラー応答なら既定値へ落ちる', async () => {
    stubFetch(() => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }))

    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
  })

  it('通信自体が失敗しても既定値で画面を出す', async () => {
    stubFetch(() => Promise.reject(new Error('offline')))

    await expect(loadUiSettings()).resolves.toEqual(FALLBACK_UI_SETTINGS)
  })

  it('前段が閉じていれば、最初の画面からメンテナンスの画面にする（ADR-0080 §10）', async () => {
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

  it('アプリ自身の 503 や本文の読めない 503 はメンテナンスとは扱わない', async () => {
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
