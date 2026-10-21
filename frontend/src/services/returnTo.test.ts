/**
 * サインインの往復で行き先を落とさない（ADR-0055）。
 */
import { describe, expect, it } from 'vitest'

import { sanitizeRedirectTo, signInPathFor } from './returnTo'

describe('sanitizeRedirectTo', () => {
  it('自サイト内の絶対パスはクエリごと通す', () => {
    expect(sanitizeRedirectTo('/items?q=a%2Fb')).toBe('/items?q=a%2Fb')
  })

  it.each([
    [null],
    [''],
    ['items'],
    ['https://evil.example/'],
    ['//evil.example/'],
    ['/\\evil.example/'],
    ['/items\r\nSet-Cookie: x'],
    [`/${'a'.repeat(255)}`],
  ])('外を指す・形の崩れた・長すぎる値（%j）は着地へ倒す', (candidate) => {
    expect(sanitizeRedirectTo(candidate)).toBe('/')
  })
})

describe('signInPathFor', () => {
  it('開こうとしていた経路とクエリを redirect_to に載せる', () => {
    expect(signInPathFor({ pathname: '/items', search: '?q=a&page=2' })).toBe(
      '/login?redirect_to=%2Fitems%3Fq%3Da%26page%3D2',
    )
  })

  it('着地から来たときは行き先を付けない', () => {
    expect(signInPathFor({ pathname: '/', search: '' })).toBe('/login')
  })
})
