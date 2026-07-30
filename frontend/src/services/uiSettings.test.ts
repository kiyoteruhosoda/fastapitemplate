/** 画面初期設定の取得（サーバーへ到達できない場合の保険を含む）。 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FALLBACK_UI_SETTINGS, loadUiSettings } from './uiSettings'

function stubFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal('fetch', vi.fn(impl))
}

describe('loadUiSettings', () => {
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
})
