/** API クライアントのトークン保持とエラーコード変換。 */
import { beforeEach, describe, expect, it } from 'vitest'

import { ApiError, clearTokens, errorMessageKey, hasTokens, setTokens } from './api'

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

describe('トークンの保持', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('保存前は未保持', () => {
    expect(hasTokens()).toBe(false)
  })

  it('保存すると保持と判定される', () => {
    setTokens('access', 'refresh')
    expect(hasTokens()).toBe(true)
  })

  it('消すと未保持に戻る', () => {
    setTokens('access', 'refresh')
    clearTokens()
    expect(hasTokens()).toBe(false)
  })
})
