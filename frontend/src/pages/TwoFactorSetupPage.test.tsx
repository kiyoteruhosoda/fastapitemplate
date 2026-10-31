/** 二要素認証の登録の画面（ADR-0093）。確定したらトークンを更新して /me を読み直す。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { AuthProvider, type Me, useAuth } from '../store/AuthContext'
import { TwoFactorSetupPage } from './TwoFactorSetupPage'

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: [],
  roles: [],
  active_role: null,
  has_password: true,
  rp_logout_enabled: false,
  two_factor_setup_required: true,
}

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))

vi.mock('../services/api', () => ({
  ApiError: class extends Error {},
  api: { get: apiGet, post: apiPost },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function Gate() {
  const { user } = useAuth()
  if (!user) return null
  return user.two_factor_setup_required ? <TwoFactorSetupPage /> : <p>opened screen</p>
}

describe('TwoFactorSetupPage', () => {
  let me: Me

  beforeEach(() => {
    vi.clearAllMocks()
    me = ME
    apiGet.mockImplementation((path: string) =>
      path === '/api/auth/me'
        ? Promise.resolve(me)
        : Promise.resolve({ enabled: false, enrolling: false, required: true }),
    )
    apiPost.mockImplementation((path: string) => {
      if (path.endsWith('/enrollment'))
        return Promise.resolve({ secret: 'ABC', otpauth_uri: 'otpauth://x', qr_code: 'data:,' })
      if (path === '/api/auth/refresh') me = { ...ME, two_factor_setup_required: false }
      return Promise.resolve({})
    })
  })

  it('確定するとトークンを更新し、開こうとしていた画面が出る', async () => {
    render(
      <MemoryRouter>
        <I18nProvider settings={SETTINGS}>
          <AuthProvider>
            <ToastProvider>
              <Gate />
            </ToastProvider>
          </AuthProvider>
        </I18nProvider>
      </MemoryRouter>,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Set up' }))
    fireEvent.change(await screen.findByLabelText('Verification code'), {
      target: { value: '123456' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => {
      expect(screen.getByText('opened screen')).toBeInTheDocument()
    })
    expect(apiPost).toHaveBeenCalledWith('/api/auth/refresh')
  })
})
