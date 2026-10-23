/**
 * 前段（edge）が閉じていると答えたことの受け取り（ADR-0067）。
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

/** title・body を足す前の edge が返す形（task #663 より前）。 */
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
  it('メンテナンスの宣言の文言を読む', () => {
    expect(outageFrom(503, MAINTENANCE)).toEqual({
      reason: 'maintenance',
      title: 'T',
      body: 'B',
      message: 'Test.',
      until: '2026-10-28T19:30:00Z',
    })
  })

  it('古い edge の形（title・body 無し）でも閉じていると読む', () => {
    expect(outageFrom(503, OLD_MAINTENANCE)).toMatchObject({
      reason: 'maintenance',
      title: null,
      body: null,
      message: 'Test.',
    })
  })

  it('上流が居ないだけのときは stopped', () => {
    expect(outageFrom(503, { error: 'service_unavailable', reason: 'stopped', host: 'x' })).toEqual(
      { reason: 'stopped', title: null, body: null, message: null, until: null },
    )
  })

  it('アプリ自身のエラーの形や 503 以外は閉じているとは扱わない', () => {
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

  it('503 の宣言なら閉じた状態にし、通れば外す', async () => {
    fetchMock.mockReturnValueOnce(respond(503, MAINTENANCE))
    await expect(checkService()).resolves.toBe('closed')
    expect(currentOutage()?.title).toBe('T')

    fetchMock.mockReturnValueOnce(respond(200, {}))
    await expect(checkService()).resolves.toBe('open')
    expect(currentOutage()).toBeNull()
  })

  it('届かないときは状態を変えない', async () => {
    reportOutage({ reason: 'maintenance', title: null, body: null, message: null, until: null })
    fetchMock.mockRejectedValueOnce(new Error('offline'))

    await expect(checkService()).resolves.toBe('unknown')
    expect(currentOutage()).not.toBeNull()
  })

  it('保存された答えを使わない', async () => {
    fetchMock.mockReturnValueOnce(respond(200, {}))
    await checkService()
    expect((fetchMock.mock.calls[0]?.[1] as RequestInit).cache).toBe('no-store')
  })
})

/** 遅れて読み込む部品の失敗（AC6）。 */
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

  it('閉じているならメンテナンスの画面にし、開いたら読み込み直す', async () => {
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

  it('ただの失敗なら何もしない（エラーは今までどおり投げさせる）', async () => {
    fetchMock.mockReturnValueOnce(respond(200, {}))
    const event = failLazyLoad()
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    expect(event.defaultPrevented).toBe(false)
    expect(currentOutage()).toBeNull()
    expect(reload).not.toHaveBeenCalled()
  })

  it('アプリ自身の 503 はメンテナンスとは扱わない', async () => {
    fetchMock.mockReturnValueOnce(respond(503, { detail: { error: 'x' } }))
    failLazyLoad()
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1)
    })

    expect(currentOutage()).toBeNull()
  })
})
