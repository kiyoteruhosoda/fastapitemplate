/**
 * セキュリティ画面（`/profile/security`）。
 *
 * パスワード変更・二要素認証・パスキーが 1 つの画面に並ぶこと（ADR-0020）と、
 * それぞれが正しい API を叩くことを確認する。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { AuthProvider, type Me, useAuth } from '../store/AuthContext'
import { SecurityPage } from './SecurityPage'

/** 実アプリと同じく、`/me` の解決後にだけページをマウントする（RequireAuth 相当）。 */
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

/** この画面が開いたときに引く 3 本（本人・二要素認証の状態・パスキーの一覧）。 */
function respondToGet(path: string, me: Me = ME) {
  if (path === '/api/auth/me') return Promise.resolve(me)
  if (path === '/api/account/security/two-factor')
    return Promise.resolve({ enabled: false, enrolling: false })
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

  it('パスワード変更・二要素認証・パスキーが 1 つの画面に並ぶ', async () => {
    await renderPage()

    expect(screen.getByRole('heading', { name: 'Change password' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Two-factor authentication' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Passkeys' })).toBeInTheDocument()
    expect(screen.getByText('No passkeys registered yet.')).toBeInTheDocument()
    // プロフィールへ戻る導線がある
    expect(screen.getByRole('link', { name: 'Back to profile' })).toHaveAttribute(
      'href',
      '/profile',
    )
  })

  it('パスワードを持たない利用者には変更フォームを出さない', async () => {
    // ⚠ 出すと、「今のパスワード」を入力できない相手に絶対に通らない入力欄を見せる
    //   ことになる（ADR-0038）。
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

  it('パスワードを変更すると POST /api/auth/change-password が飛ぶ', async () => {
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

  it('二要素認証を設定すると QR と確認コードの入力欄が出る', async () => {
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

  it('登録済みのパスキーを一覧に出し、削除できる', async () => {
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
