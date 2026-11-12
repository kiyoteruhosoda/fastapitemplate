/**
 * Which entry points the login page shows (ADR-0077 §1 / ADR-0076 §3).
 *
 * Whether to show the SSO button or the password fields is **asked of the server**
 * (`GET /api/auth/sso/provider`). Settings can change after startup, so it is not baked into the page.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import { AuthProvider } from '../store/AuthContext'
import { LoginPage } from './LoginPage'

const { fetchSsoProvider, startSsoLogin } = vi.hoisted(() => ({
  fetchSsoProvider: vi.fn(),
  startSsoLogin: vi.fn(),
}))

vi.mock('../services/sso', () => ({ fetchSsoProvider, startSsoLogin }))

vi.mock('../services/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
  ApiError: class extends Error {},
  errorMessageKey: () => 'error.unknown_error',
  clearTokens: vi.fn(),
  hasTokens: () => false,
  setTokens: vi.fn(),
}))

vi.mock('../services/webauthn', () => ({
  assertPasskey: vi.fn(),
  isPasskeyCancellation: () => false,
  isPasskeySupported: () => true,
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderPage(entry = '/login') {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <I18nProvider settings={SETTINGS}>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    window.sessionStorage.clear()
    // These tests are about which entry points show. Treat the no-click sign-in attempt
    // (ADR-0077 §9) as already done
    window.sessionStorage.setItem('ssoSilentTried', '1')
  })

  it('without SSO shows no button and allows password sign-in', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: false,
      display_name: '',
      local_login_enabled: true,
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /Sign in with Nolumia/ })).not.toBeInTheDocument()
  })

  it('with SSO shows the button (named after the IdP)', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Sign in with Nolumia' })).toBeInTheDocument()
    })
    // Both is the default. The password entry is still there (ADR-0076 §3).
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('shows neither password fields nor passkey when the local entry is closed', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: false,
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Sign in with Nolumia' })).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in with a passkey' })).not.toBeInTheDocument()
  })

  it('shows no entry point until the request gets through, then shows the IdP entry', async () => {
    // During a release the server is unreachable. Showing the default entry (password fields) would
    // leave the user stranded on a page without the IdP button once the server is back.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    fetchSsoProvider.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: false,
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/Cannot reach the server/)).toBeInTheDocument()
    })
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()

    await vi.advanceTimersByTimeAsync(5000)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Sign in with Nolumia' })).toBeInTheDocument()
    })
    vi.useRealTimers()
  })

  it('shows ?signed_out as a message after signing out at the IdP', async () => {
    // Note: without it, it cannot be told apart from being kicked out by expiry (ADR-0077 §2).
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
      rp_logout_enabled: true,
    })
    renderPage('/login?signed_out=1')

    await waitFor(() => {
      expect(screen.getByText('You are signed out.')).toBeInTheDocument()
    })
  })

  it('shows ?sso_error as a message when the server-side round trip fails', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    renderPage('/login?sso_error=sso_state_invalid')

    await waitFor(() => {
      expect(
        screen.getByText(
          'The sign-in attempt expired or was started in another browser. Please try again.',
        ),
      ).toBeInTheDocument()
    })
  })

  it.each([
    ['/login?redirect_to=%2Fitems%3Fq%3Da', '/items?q=a'],
    ['/login', '/'],
    ['/login?redirect_to=https%3A%2F%2Fevil.example%2F', '/'],
  ])('passes the page being opened to the SSO entry (%s -> %s. ADR-0077 §8)', async (entry, expected) => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    renderPage(entry)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Nolumia' }))
    expect(startSsoLogin).toHaveBeenCalledWith(expected, undefined)
  })

  it('on a tenant entry links to the IdP and password reset of that tenant (ADR-0079 §4)', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    render(
      <MemoryRouter initialEntries={['/t/acme/login']}>
        <I18nProvider settings={SETTINGS}>
          <AuthProvider>
            <Routes>
              <Route path="/t/:tenant/login" element={<LoginPage />} />
            </Routes>
          </AuthProvider>
        </I18nProvider>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Nolumia' }))
    expect(fetchSsoProvider).toHaveBeenCalledWith('acme')
    expect(startSsoLogin).toHaveBeenCalledWith('/', 'acme')
    expect(screen.getByRole('link', { name: /forgot/i })).toHaveAttribute(
      'href',
      '/t/acme/forgot-password',
    )
  })

  describe('no-click sign-in attempt (ADR-0077 §9)', () => {
    const PROVIDER = { enabled: true, display_name: 'Nolumia', local_login_enabled: true }

    beforeEach(() => {
      window.sessionStorage.clear()
      fetchSsoProvider.mockResolvedValue(PROVIDER)
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('on open sends to the IdP with prompt=none without rendering entry points (keeps the destination)', async () => {
      renderPage('/login?redirect_to=%2Fitems')

      await waitFor(() => {
        expect(startSsoLogin).toHaveBeenCalledWith('/items', undefined, { silent: true })
      })
      expect(screen.queryByRole('button', { name: 'Sign in with Nolumia' })).not.toBeInTheDocument()
      expect(window.sessionStorage.getItem('ssoSilentTried')).toBe('1')
    })

    it('after returning from an attempt shows the normal entry points without an error', async () => {
      renderPage('/login?sso_silent=declined&redirect_to=%2Fitems')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(document.querySelector('.error')).toBeNull()
    })

    it('tries once more when the returned page is reloaded (ADR-0077 §10)', async () => {
      window.sessionStorage.setItem('ssoSilentTried', '1')
      vi.spyOn(window.performance, 'getEntriesByType').mockReturnValue([
        { type: 'reload' } as PerformanceNavigationTiming,
      ])
      renderPage('/login?sso_silent=declined&redirect_to=%2Fitems')

      await waitFor(() => {
        expect(startSsoLogin).toHaveBeenCalledWith('/items', undefined, { silent: true })
      })
    })

    it('does not try on reload after signing out', async () => {
      window.localStorage.setItem('ssoSignedOut', '1')
      vi.spyOn(window.performance, 'getEntriesByType').mockReturnValue([
        { type: 'reload' } as PerformanceNavigationTiming,
      ])
      renderPage('/login?sso_silent=declined')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('does not try if already tried in this tab', async () => {
      window.sessionStorage.setItem('ssoSilentTried', '1')
      renderPage('/login')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('does not try after signing out', async () => {
      window.localStorage.setItem('ssoSignedOut', '1')
      renderPage('/login')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('does not try when an error is attached', async () => {
      renderPage('/login?sso_error=sso_account_not_linked')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('on a tenant entry tries with the IdP of that tenant (ADR-0079 §4)', async () => {
      render(
        <MemoryRouter initialEntries={['/t/acme/login']}>
          <I18nProvider settings={SETTINGS}>
            <AuthProvider>
              <Routes>
                <Route path="/t/:tenant/login" element={<LoginPage />} />
              </Routes>
            </AuthProvider>
          </I18nProvider>
        </MemoryRouter>,
      )

      await waitFor(() => {
        expect(startSsoLogin).toHaveBeenCalledWith('/', 'acme', { silent: true })
      })
    })

    // Note: trying without being able to write the marker means that on return it is unknown
    //   whether it was tried, and the round trips never stop
    it.each([
      [
        'writing throws',
        () => {
          throw new DOMException('quota', 'QuotaExceededError')
        },
      ],
      ['writing does not persist', () => undefined],
    ])('does not try in a browser that cannot write the marker (%s)', async (_case, setItem) => {
      const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(setItem)
      try {
        renderPage('/login')

        expect(
          await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
        ).toBeInTheDocument()
        expect(startSsoLogin).not.toHaveBeenCalled()
      } finally {
        spy.mockRestore()
      }
    })

    it('does not try in a browser that cannot read the marker either', async () => {
      // Only the attempt marker is unreadable (language and appearance preferences are treated as absent)
      const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => {
        if (key === 'ssoSignedOut' || key === 'ssoSilentTried') {
          throw new DOMException('denied', 'SecurityError')
        }
        return null
      })
      try {
        renderPage('/login')

        expect(
          await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
        ).toBeInTheDocument()
        expect(startSsoLogin).not.toHaveBeenCalled()
      } finally {
        spy.mockRestore()
      }
    })

    it('does not try when SSO is disabled', async () => {
      fetchSsoProvider.mockResolvedValue({ ...PROVIDER, enabled: false })
      renderPage('/login')

      expect(await screen.findByLabelText('Password')).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })
  })
})
