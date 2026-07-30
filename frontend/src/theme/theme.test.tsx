/** テーマの初期選択・OS 追従・切り替えの反映。 */
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UiSettings } from '../services/uiSettings'
import { withSuppressedRenderErrors } from '../test-support/renderErrors'
import { ThemeProvider, useTheme } from './index'

function settingsOf(overrides: Partial<UiSettings> = {}): UiSettings {
  return { languages: ['en'], default_locale: 'en', default_theme: 'system', ...overrides }
}

/**
 * `matchMedia` を差し替え、OS 側の切り替えを発火できるようにする。
 * jsdom の実装は `change` を通知しないため、購読の検証には差し替えが必要。
 */
function stubMatchMedia(matches: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>()
  const query = {
    matches,
    addEventListener: (_type: string, handle: (event: MediaQueryListEvent) => void) => {
      listeners.add(handle)
    },
    removeEventListener: (_type: string, handle: (event: MediaQueryListEvent) => void) => {
      listeners.delete(handle)
    },
  }
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => query),
  )
  return {
    emit(next: boolean) {
      query.matches = next
      for (const handle of listeners) {
        handle({ matches: next } as MediaQueryListEvent)
      }
    },
    listenerCount: () => listeners.size,
  }
}

function Probe() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button
        onClick={() => {
          setTheme('light')
        }}
      >
        light
      </button>
    </div>
  )
}

function renderWith(settings: UiSettings) {
  return render(
    <ThemeProvider settings={settings}>
      <Probe />
    </ThemeProvider>,
  )
}

describe('ThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    document.documentElement.removeAttribute('data-theme')
  })

  it('利用者の選択（localStorage）を最優先する', () => {
    stubMatchMedia(false)
    localStorage.setItem('theme', 'dark')
    renderWith(settingsOf({ default_theme: 'light' }))
    expect(screen.getByTestId('theme').textContent).toBe('dark')
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('未選択ならサーバーの既定値を使う', () => {
    stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'light' }))
    expect(screen.getByTestId('theme').textContent).toBe('light')
  })

  it('既定値が不正なら system に落ちる', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'solarized' }))
    expect(screen.getByTestId('theme').textContent).toBe('system')
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('system のときは OS の配色を解決結果にする', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('system のまま OS 側が切り替わると追従する', () => {
    const media = stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(screen.getByTestId('resolved').textContent).toBe('light')

    act(() => {
      media.emit(true)
    })
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('明示的に選んだテーマは OS の変化に影響されない', () => {
    const media = stubMatchMedia(false)
    localStorage.setItem('theme', 'light')
    renderWith(settingsOf())

    act(() => {
      media.emit(true)
    })
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('解決結果を <html data-theme> と colorScheme へ反映する', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('選択を localStorage に保存する', () => {
    stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'dark' }))

    act(() => {
      screen.getByRole('button', { name: 'light' }).click()
    })
    expect(localStorage.getItem('theme')).toBe('light')
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('アンマウント時に OS の購読を解除する', () => {
    const media = stubMatchMedia(false)
    const { unmount } = renderWith(settingsOf())
    expect(media.listenerCount()).toBe(1)

    unmount()
    expect(media.listenerCount()).toBe(0)
  })
})

describe('useTheme', () => {
  it('Provider の外で使うと例外を投げる', () => {
    stubMatchMedia(false)
    try {
      withSuppressedRenderErrors(() => {
        expect(() => render(<Probe />)).toThrow(/ThemeProvider/)
      })
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
