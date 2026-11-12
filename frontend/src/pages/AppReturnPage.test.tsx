/**
 * Guidance to return to the app (S16. ADR-0081 §2).
 *
 * Only when an authorization code is present, a button that reopens the same URL is shown
 * (the Custom Tab does not open the app on an automatic navigation, so the user's tap reopens it).
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
