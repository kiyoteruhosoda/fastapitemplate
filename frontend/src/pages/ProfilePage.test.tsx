/**
 * Profile self-editing (email address, display name) and placement of display settings.
 *
 * Checks that saving sends PUT /api/auth/me, that success shows a toast and refetches /me,
 * that language and theme selection appear on this page (ADR-0080 §3), and that sign-in
 * methods are on a separate page with only an entry point here (ADR-0080 §4).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type { Me } from '../store/AuthContext'
import { AuthProvider, useAuth } from '../store/AuthContext'
import { ThemeProvider } from '../theme'
import { ProfilePage } from './ProfilePage'

/** As in the real app, mount the page only after /me resolves (equivalent to RequireAuth). */
function Gate() {
  const { user } = useAuth()
  if (!user) return null
  return <ProfilePage />
}

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: ['dashboard:view'],
  roles: ['manager', 'member'],
  active_role: 'member',
  has_password: true,
  rp_logout_enabled: false,
}

const { apiGet, apiPut, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  apiPost: vi.fn(),
}))

// Tokens travel in cookies, so this layer no longer has a place to hold them (ADR-0076 §4).
vi.mock('../services/api', () => ({
  api: { get: apiGet, put: apiPut, post: apiPost },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

/** The current location (to see whether it was sent to sign in again). */
function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>
}

async function renderPage() {
  render(
    <MemoryRouter initialEntries={['/profile']}>
      <I18nProvider settings={SETTINGS}>
        <ThemeProvider settings={SETTINGS}>
          <AuthProvider>
            <ToastProvider>
              <Gate />
              <LocationProbe />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
  await waitFor(() => {
    expect(screen.getByLabelText('Email')).toHaveValue('admin@example.com')
  })
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockResolvedValue(ME)
    apiPut.mockResolvedValue(ME)
    // jsdom has no matchMedia (ThemeProvider looks at the OS color scheme).
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    )
  })

  it('saving email and display name sends PUT /api/auth/me and refetches /me', async () => {
    await renderPage()

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } })
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'renamed' } })
    apiGet.mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/auth/me', {
        email: 'new@example.com',
        username: 'renamed',
      })
    })
    // After saving a toast appears and the auth state (/me) is refetched
    await waitFor(() => {
      expect(screen.getByText('Saved.')).toBeInTheDocument()
    })
    expect(apiGet).toHaveBeenCalledWith('/api/auth/me')
  })

  it('shows an error toast when saving fails', async () => {
    await renderPage()
    apiPut.mockRejectedValueOnce(new Error('boom'))

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Something went wrong.')).toBeInTheDocument()
    })
  })

  it('on a re-sign-in request notifies, goes to login and keeps this page as the return target', async () => {
    await renderPage()
    apiPut.mockRejectedValueOnce(
      Object.assign(new Error('403'), { code: 'reauthentication_required' }),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/login?redirect_to=%2Fprofile')
    })
    expect(
      screen.getByText('For your security, please sign in again and retry.'),
    ).toBeInTheDocument()
  })

  it('for users linked to an IdP shows no inputs and points them to the IdP', async () => {
    apiGet.mockResolvedValue({ ...ME, profile_managed_by_idp: true })
    render(
      <MemoryRouter initialEntries={['/profile']}>
        <I18nProvider settings={SETTINGS}>
          <ThemeProvider settings={SETTINGS}>
            <AuthProvider>
              <ToastProvider>
                <Gate />
              </ToastProvider>
            </AuthProvider>
          </ThemeProvider>
        </I18nProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText(/Change your name and email/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Username')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
    expect(screen.getByText(/admin@example.com/)).toBeInTheDocument()
  })

  it('shows language and theme selection on this page', async () => {
    await renderPage()

    expect(screen.getByLabelText('Language')).toBeInTheDocument()
    expect(screen.getByLabelText('Theme')).toBeInTheDocument()
  })

  it('keeps sign-in methods on a separate page with only an entry point', async () => {
    await renderPage()

    expect(screen.getByRole('link', { name: 'Open security settings' })).toHaveAttribute(
      'href',
      '/profile/security',
    )
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument()
  })
})
