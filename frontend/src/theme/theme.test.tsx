/** Initial theme selection, following the OS, and applying a switch. */
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UiSettings } from '../services/uiSettings'
import { withSuppressedRenderErrors } from '../test-support/renderErrors'
import { ThemeProvider, useTheme } from './index'

function settingsOf(overrides: Partial<UiSettings> = {}): UiSettings {
  return { languages: ['en'], default_locale: 'en', default_theme: 'system', ...overrides }
}

/**
 * Replace `matchMedia` so an OS-side change can be fired.
 * jsdom's implementation never emits `change`, so testing the subscription needs a stub.
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

/** A browser that cannot read or write storage (e.g. Chrome with site data blocked). */
function blockStorage(): () => void {
  const denied = () => {
    throw new DOMException('denied', 'SecurityError')
  }
  const spies = [
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(denied),
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(denied),
  ]
  return () => {
    for (const spy of spies) spy.mockRestore()
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

  it('prefers the choice the user saved (localStorage) above all', () => {
    stubMatchMedia(false)
    localStorage.setItem('theme', 'dark')
    renderWith(settingsOf({ default_theme: 'light' }))
    expect(screen.getByTestId('theme').textContent).toBe('dark')
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('uses the server default when nothing is chosen', () => {
    stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'light' }))
    expect(screen.getByTestId('theme').textContent).toBe('light')
  })

  it('falls back to system when the default is invalid', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'solarized' }))
    expect(screen.getByTestId('theme').textContent).toBe('system')
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('resolves to the OS palette when system is chosen', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('follows an OS-side change while on system', () => {
    const media = stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(screen.getByTestId('resolved').textContent).toBe('light')

    act(() => {
      media.emit(true)
    })
    expect(screen.getByTestId('resolved').textContent).toBe('dark')
  })

  it('an explicitly chosen theme is not affected by OS changes', () => {
    const media = stubMatchMedia(false)
    localStorage.setItem('theme', 'light')
    renderWith(settingsOf())

    act(() => {
      media.emit(true)
    })
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('applies the resolved theme to <html data-theme> and colorScheme', () => {
    stubMatchMedia(true)
    renderWith(settingsOf({ default_theme: 'system' }))
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('saves the choice to localStorage', () => {
    stubMatchMedia(false)
    renderWith(settingsOf({ default_theme: 'dark' }))

    act(() => {
      screen.getByRole('button', { name: 'light' }).click()
    })
    expect(localStorage.getItem('theme')).toBe('light')
    expect(screen.getByTestId('resolved').textContent).toBe('light')
  })

  it('renders and can still switch when storage is unavailable', () => {
    stubMatchMedia(false)
    const restore = blockStorage()
    try {
      renderWith(settingsOf({ default_theme: 'dark' }))
      expect(screen.getByTestId('theme').textContent).toBe('dark')

      act(() => {
        screen.getByRole('button', { name: 'light' }).click()
      })
      expect(screen.getByTestId('resolved').textContent).toBe('light')
    } finally {
      restore()
    }
  })

  it('unsubscribes from the OS on unmount', () => {
    const media = stubMatchMedia(false)
    const { unmount } = renderWith(settingsOf())
    expect(media.listenerCount()).toBe(1)

    unmount()
    expect(media.listenerCount()).toBe(0)
  })
})

describe('useTheme', () => {
  it('throws when used outside the Provider', () => {
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
