/**
 * アプリへ戻る案内（S16。ADR-0046）。
 *
 * 認可コードが付いているときだけ、同じ URL をもう一度開くボタンを出す
 * （Custom Tab が自動の移動ではアプリを開かないため、利用者のタップで開き直す）。
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { I18nProvider } from '../i18n'
import { AppReturnPage } from './AppReturnPage'

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderAt(path: string) {
  return render(
    <I18nProvider settings={SETTINGS}>
      <MemoryRouter initialEntries={[path]}>
        <AppReturnPage />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('AppReturnPage', () => {
  it('offers to reopen the same URL when an authorization code is present', () => {
    renderAt('/app/oauth2redirect?code=abc&state=xyz')
    const link = screen.getByRole('link', { name: /return to the app|アプリに戻って/i })
    expect(link).toHaveAttribute('href', window.location.href)
  })

  it('shows only the guidance without a code', () => {
    renderAt('/app/oauth2redirect')
    expect(screen.queryByRole('link', { name: /return to the app|アプリに戻って/i })).toBeNull()
    expect(screen.getByRole('link', { name: /web/i })).toBeInTheDocument()
  })
})
