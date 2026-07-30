/** 言語の初期選択・切り替え・プレースホルダ差し込み。 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import type { UiSettings } from '../services/uiSettings'
import { withSuppressedRenderErrors } from '../test-support/renderErrors'
import { I18nProvider, useI18n } from './index'

function settingsOf(overrides: Partial<UiSettings> = {}): UiSettings {
  return { languages: ['en', 'ja'], default_locale: 'en', default_theme: 'system', ...overrides }
}

function Probe() {
  const { locale, locales, t } = useI18n()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="locales">{locales.join(',')}</span>
      <span data-testid="missing">{t('no.such.key')}</span>
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

  it('利用者の選択（localStorage）を最優先する', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf({ default_locale: 'en' }))
    expect(screen.getByTestId('locale').textContent).toBe('ja')
  })

  it('選べない言語が保存されていればサーバーの既定値へ落ちる', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf({ languages: ['en'], default_locale: 'en' }))
    expect(screen.getByTestId('locale').textContent).toBe('en')
  })

  it('未知の言語しか設定されていなければ en に落ちる', () => {
    renderWith(settingsOf({ languages: ['fr'], default_locale: 'fr' }))
    expect(screen.getByTestId('locale').textContent).toBe('en')
    expect(screen.getByTestId('locales').textContent).toBe('en')
  })

  it('<html lang> を選択中の言語に合わせる', () => {
    localStorage.setItem('locale', 'ja')
    renderWith(settingsOf())
    expect(document.documentElement.lang).toBe('ja')
  })

  it('辞書に無いキーはキー自身を返す', () => {
    renderWith(settingsOf())
    expect(screen.getByTestId('missing').textContent).toBe('no.such.key')
  })
})

describe('t のプレースホルダ差し込み', () => {
  function Interpolated({ params }: { params: Record<string, string | number> }) {
    const { t } = useI18n()
    return <span data-testid="out">{t('{greeting}, {name}! ({count})', params)}</span>
  }

  beforeEach(() => {
    localStorage.clear()
  })

  it('{name} 形式のプレースホルダを置き換える', () => {
    render(
      <I18nProvider settings={settingsOf()}>
        <Interpolated params={{ greeting: 'Hello', name: 'Ada', count: 3 }} />
      </I18nProvider>,
    )
    expect(screen.getByTestId('out').textContent).toBe('Hello, Ada! (3)')
  })

  it('渡されなかったプレースホルダはそのまま残す', () => {
    render(
      <I18nProvider settings={settingsOf()}>
        <Interpolated params={{ greeting: 'Hi' }} />
      </I18nProvider>,
    )
    expect(screen.getByTestId('out').textContent).toBe('Hi, {name}! ({count})')
  })
})

describe('useI18n', () => {
  it('Provider の外で使うと例外を投げる', () => {
    withSuppressedRenderErrors(() => {
      expect(() => render(<Probe />)).toThrow(/I18nProvider/)
    })
  })
})
