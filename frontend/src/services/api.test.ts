/** API クライアントのエラーコード変換と、CSRF トークンの送り方。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api, errorMessageKey } from './api'

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
 * トークンは持たない（ADR-0028）。この層が気にするのは Cookie を送ることと、
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
