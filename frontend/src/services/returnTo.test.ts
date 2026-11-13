/**
 * Keep the destination across the sign-in round trip (ADR-0077 §8).
 */
import { describe, expect, it } from 'vitest'

import { sanitizeRedirectTo, signInPathFor } from './returnTo'

describe('sanitizeRedirectTo', () => {
  it('passes absolute in-site paths through with their query', () => {
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
  ])('falls back to landing for outside, malformed, or too-long values (%j)', (candidate) => {
    expect(sanitizeRedirectTo(candidate)).toBe('/')
  })
})

describe('signInPathFor', () => {
  it('puts the path and query being opened into redirect_to', () => {
    expect(signInPathFor({ pathname: '/items', search: '?q=a&page=2' })).toBe(
      '/login?redirect_to=%2Fitems%3Fq%3Da%26page%3D2',
    )
  })

  it('adds no destination when coming from the landing page', () => {
    expect(signInPathFor({ pathname: '/', search: '' })).toBe('/login')
  })
})
