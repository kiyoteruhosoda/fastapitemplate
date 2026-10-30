/** API クライアントのエラーコード変換と、CSRF トークンの送り方。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, errorMessageKey } from './api'
import { currentOutage, reportOutage, resetOutageForTests } from './maintenance'

describe('errorMessageKey', () => {
  it('ApiError のコードを i18n キーへ変換する', () => {
    expect(errorMessageKey(new ApiError(401, 'invalid_token'))).toBe('error.invalid_token')
  })

  it('API 以外の例外は unknown_error に丸める', () => {
    expect(errorMessageKey(new Error('boom'))).toBe('error.unknown_error')
  })

  it('例外でない値でも落ちない', () => {
    expect(errorMessageKey(undefined)).toBe('error.unknown_error')
    expect(errorMessageKey('invalid_token')).toBe('error.unknown_error')
  })
})

/**
 * トークンは持たない（ADR-0076 §4）。この層が気にするのは Cookie を送ることと、
 * 更新系に CSRF の二重送信トークンを載せることだけ。
 */
describe('リクエストの組み立て', () => {
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

  it('Cookie を送る（トークンは Cookie に載っているため）', async () => {
    await api.get('/api/auth/me')
    expect(initOf().credentials).toBe('same-origin')
  })

  it('読み取りには CSRF トークンを載せない', async () => {
    await api.get('/api/auth/me')
    expect(initOf().headers).not.toHaveProperty('X-CSRF-Token')
  })

  it('更新系には Cookie から読んだ CSRF トークンを載せる', async () => {
    await api.post('/api/items', { name: 'x' })
    expect((initOf().headers as Record<string, string>)['X-CSRF-Token']).toBe('the-token')
  })

  it('Authorization ヘッダーは付けない（手元にトークンを持たないため）', async () => {
    await api.post('/api/items', { name: 'x' })
    expect(initOf().headers).not.toHaveProperty('Authorization')
  })
})

/** 前段（edge）が閉じていると答えた 503（ADR-0080 §10）。 */
describe('トークンの更新', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('同時に 401 になった要求は 1 本の更新を待つ', async () => {
    let refreshed = false
    const fetchMock = vi.fn((path: string) => {
      if (path === '/api/auth/refresh') {
        refreshed = true
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) })
      }
      const status = refreshed ? 200 : 401
      return Promise.resolve({ ok: status === 200, status, json: () => Promise.resolve({}) })
    })
    vi.stubGlobal('fetch', fetchMock)

    await Promise.all([api.get('/api/a'), api.get('/api/b')])

    const refreshes = fetchMock.mock.calls.filter(([path]) => path === '/api/auth/refresh')
    expect(refreshes).toHaveLength(1)
  })
})

describe('閉じている前段の 503', () => {
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

  it('メンテナンスの画面へ知らせ、service_unavailable で投げる', async () => {
    respond(503, { error: 'service_unavailable', reason: 'maintenance', message: 'Test.' })

    await expect(api.get('/api/items')).rejects.toMatchObject({
      status: 503,
      code: 'service_unavailable',
    })
    expect(currentOutage()).toMatchObject({ reason: 'maintenance', message: 'Test.' })
  })

  it('アプリ自身の 503 はメンテナンスとは扱わない', async () => {
    respond(503, { detail: { error: 'restart_request_failed' } })

    await expect(api.get('/api/items')).rejects.toMatchObject({ code: 'restart_request_failed' })
    expect(currentOutage()).toBeNull()
  })

  it('答えが返れば閉じた状態を外す', async () => {
    reportOutage({ reason: 'stopped', title: null, body: null, message: null, until: null })
    respond(200, {})

    await api.get('/api/items')

    expect(currentOutage()).toBeNull()
  })
})
