/**
 * Security page (`/profile/security`).
 *
 * Checks that password change, two-factor authentication, passkeys and IdP linking are on one
 * page (ADR-0080 §4 / ADR-0077 §5),
 * and that each calls the right API.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { AuthProvider, type Me, useAuth } from '../store/AuthContext'
import { SecurityPage } from './SecurityPage'

/** As in the real app, mount the page only after `/me` resolves (equivalent to RequireAuth). */
function Gate() {
  const { user } = useAuth()
  if (!user) return null
  return <SecurityPage />
}

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: [],
  roles: [],
  active_role: null,
  has_password: true,
  rp_logout_enabled: false,
}

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost, delete: apiDelete },
  errorMessageKey: () => 'error.unknown_error',
}))

vi.mock('../services/webauthn', () => ({
  createPasskey: vi.fn(),
  isPasskeyCancellation: () => false,
  isPasskeySupported: () => true,
}))

/** The four requests made when this page opens (self, two-factor, link state, passkey list). */
function respondToGet(path: string, me: Me = ME) {
  if (path === '/api/auth/me') return Promise.resolve(me)
  if (path === '/api/account/security/two-factor')
    return Promise.resolve({ enabled: false, enrolling: false })
  if (path === '/api/auth/sso/link')
    return Promise.resolve({
      available: true,
      display_name: 'Example IdP',
      linked: false,
      linked_at: null,
      can_unlink: false,
    })
  return Promise.resolve([])
}

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

async function renderPage() {
  render(
    <MemoryRouter initialEntries={['/profile/security']}>
      <I18nProvider settings={SETTINGS}>
        <AuthProvider>
          <ToastProvider>
            <Gate />
          </ToastProvider>
        </AuthProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
  await waitFor(() => {
    expect(screen.getByText('Two-factor authentication is off.')).toBeInTheDocument()
  })
}

describe('SecurityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockImplementation(respondToGet)
    apiPost.mockResolvedValue({})
  })

  it('shows password change, two-factor, passkeys and linking on one page', async () => {
    await renderPage()

    expect(screen.getByRole('heading', { name: 'Change password' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Two-factor authentication' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Passkeys' })).toBeInTheDocument()
    expect(screen.getByText('No passkeys registered yet.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Single sign-on' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Link with Example IdP' })).toBeInTheDocument()
    // There is a way back to the profile
    expect(screen.getByRole('link', { name: 'Back to profile' })).toHaveAttribute(
      'href',
      '/profile',
    )
  })

  it('does not show the change form to users without a password', async () => {
    // Note: otherwise users who cannot enter a "current password" would see inputs that can never
    //   succeed (ADR-0076 §6).
    apiGet.mockImplementation((path: string) => respondToGet(path, { ...ME, has_password: false }))
    await renderPage()

    expect(screen.getByRole('heading', { name: 'Change password' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument()
    expect(
      screen.getByText(
        'You sign in with your identity provider, so there is no password to change here.',
      ),
    ).toBeInTheDocument()
  })

  it('changing the password sends POST /api/auth/change-password', async () => {
    await renderPage()

    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'old-secret' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'new-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/auth/change-password', {
        current_password: 'old-secret',
        new_password: 'new-secret',
      })
    })
    expect(screen.getByText('Saved.')).toBeInTheDocument()
  })

  it('setting up two-factor shows the QR and the confirmation code input', async () => {
    await renderPage()
    apiPost.mockResolvedValueOnce({
      secret: 'ABCDEF',
      otpauth_uri: 'otpauth://totp/x',
      qr_code: 'data:image/svg+xml;base64,AAA',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Set up' }))

    await waitFor(() => {
      expect(screen.getByAltText('Setup QR code for your authenticator app')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Verification code')).toBeInTheDocument()
  })

  it('lists registered passkeys and can delete them', async () => {
    apiGet.mockImplementation((path: string) =>
      path === '/api/account/security/two-factor'
        ? Promise.resolve({ enabled: false, enrolling: false })
        : Promise.resolve([
            {
              id: 7,
              name: 'Work laptop',
              transports: [],
              created_at: '2026-08-01T00:00:00Z',
              last_used_at: null,
            },
          ]),
    )
    apiDelete.mockResolvedValue({})
    await renderPage()

    expect(screen.getByText('Work laptop')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/account/security/passkeys/7')
    })
  })
})
