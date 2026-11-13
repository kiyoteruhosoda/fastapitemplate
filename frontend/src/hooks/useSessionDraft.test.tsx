/** Keeps drafts across the sign-in round trip (ADR-0104). */
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { clearSessionDrafts, useSessionDraft } from './useSessionDraft'

describe('useSessionDraft', () => {
  afterEach(() => {
    window.sessionStorage.clear()
  })

  it('keeps the written value when the screen is rebuilt (after the round trip)', () => {
    const first = renderHook(() => useSessionDraft<{ title: string }>('notes'))
    act(() => {
      first.result.current[1]({ title: '書きかけ' })
    })
    first.unmount()

    const again = renderHook(() => useSessionDraft<{ title: string }>('notes'))
    expect(again.result.current[0]).toEqual({ title: '書きかけ' })
  })

  it('removes it when set to null (saved or closed)', () => {
    const { result } = renderHook(() => useSessionDraft<{ title: string }>('notes'))
    act(() => {
      result.current[1]({ title: 'x' })
    })
    act(() => {
      result.current[1](null)
    })
    expect(window.sessionStorage.getItem('draft:notes')).toBeNull()
  })

  it('can be updated with a function', () => {
    const { result } = renderHook(() => useSessionDraft<{ n: number }>('count', { n: 1 }))
    act(() => {
      result.current[1]((current) => ({ n: (current?.n ?? 0) + 1 }))
    })
    expect(result.current[0]).toEqual({ n: 2 })
  })

  it('clears all drafts on sign-out (other values stay)', () => {
    window.sessionStorage.setItem('draft:a', '{}')
    window.sessionStorage.setItem('ssoSilentTried', '1')
    clearSessionDrafts()
    expect(window.sessionStorage.getItem('draft:a')).toBeNull()
    expect(window.sessionStorage.getItem('ssoSilentTried')).toBe('1')
  })
})
