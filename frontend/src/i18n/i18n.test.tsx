/** Initial language selection, switching, and placeholder substitution. */
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UiSettings } from '../services/uiSettings'
import { withSuppressedRenderErrors } from '../test-support/renderErrors'
import { I18nProvider, useI18n } from './index'

function settingsOf(overrides: Partial<UiSettings> = {}): UiSettings {
  return { languages: ['en', 'ja'], default_locale: 'en', default_theme: 'system', ...overrides }
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
  const { locale, locales, t, setLocale } = useI18n()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="locales">{locales.join(',')}</span>
      <span data-testid="missing">{t('no.such.key')}</span>
      <button
        onClick={() => {
          setLocale('ja')
        }}
      >
        ja
      </button>
    </div>
  )
}

function renderWith(settings: UiSettings) {
  return render(
    <I18nProvider settings={settings}>
      <Probe />
    </I18nProvider>,
  )
}

describe('I18nProvider', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('prefers the choice the user saved (localStorage) above all', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf({ default_locale: 'en' }))
    expect(screen.getByTestId('locale').textContent).toBe('ja')
  })

  it('falls back to the server default when the saved language is not selectable', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf({ languages: ['en'], default_locale: 'en' }))
    expect(screen.getByTestId('locale').textContent).toBe('en')
  })

  it('falls back to en when only unknown languages are configured', () => {
    renderWith(settingsOf({ languages: ['fr'], default_locale: 'fr' }))
    expect(screen.getByTestId('locale').textContent).toBe('en')
    expect(screen.getByTestId('locales').textContent).toBe('en')
  })

  it('sets <html lang> to the selected language', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf())
    expect(document.documentElement.lang).toBe('ja')
  })

  it('renders and can still switch when storage is unavailable', () => {
    const restore = blockStorage()
    try {
      renderWith(settingsOf({ languages: ['en', 'ja'] }))
      expect(screen.getByTestId('locale').textContent).toBe('en')

      act(() => {
        screen.getByRole('button', { name: 'ja' }).click()
      })
      expect(screen.getByTestId('locale').textContent).toBe('ja')
    } finally {
      restore()
    }
  })

  it('returns the key itself for a key missing from the dictionary', () => {
    renderWith(settingsOf())
    expect(screen.getByTestId('missing').textContent).toBe('no.such.key')
  })
})

describe('placeholder substitution in t', () => {
  function Interpolated({ params }: { params: Record<string, string | number> }) {
    const { t } = useI18n()
    return <span data-testid="out">{t('{greeting}, {name}! ({count})', params)}</span>
  }

  beforeEach(() => {
    localStorage.clear()
  })

  it('replaces {name}-style placeholders', () => {
    render(
      <I18nProvider settings={settingsOf()}>
        <Interpolated params={{ greeting: 'Hello', name: 'Ada', count: 3 }} />
      </I18nProvider>,
    )
    expect(screen.getByTestId('out').textContent).toBe('Hello, Ada! (3)')
  })

  it('leaves placeholders that were not passed as they are', () => {
    render(
      <I18nProvider settings={settingsOf()}>
        <Interpolated params={{ greeting: 'Hi' }} />
      </I18nProvider>,
    )
    expect(screen.getByTestId('out').textContent).toBe('Hi, {name}! ({count})')
  })
})

describe('useI18n', () => {
  it('throws when used outside the Provider', () => {
    withSuppressedRenderErrors(() => {
      expect(() => render(<Probe />)).toThrow(/I18nProvider/)
    })
  })
})
