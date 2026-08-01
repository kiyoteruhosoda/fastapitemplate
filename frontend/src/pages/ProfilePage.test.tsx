/**
 * プロフィールの自己編集（メールアドレス・表示名）と、統合した区画の配置。
 *
 * 保存が PUT /api/auth/me に飛ぶこと、成功でトーストが出て /me を引き直すこと、
 * 言語・テーマの選択（ADR-0016）とパスワード変更・二要素認証・パスキー
 * （ADR-0020）がこのページに出ることを確認する。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type { Me } from '../store/AuthContext'
import { AuthProvider, useAuth } from '../store/AuthContext'
import { ThemeProvider } from '../theme'
import { ProfilePage } from './ProfilePage'

/** 実アプリと同じく、/me の解決後にだけページをマウントする（RequireAuth 相当）。 */
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
}

const { apiGet, apiPut, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, put: apiPut, post: apiPost, delete: apiDelete },
  hasTokens: () => true,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  errorMessageKey: () => 'error.unknown_error',
}))

vi.mock('../services/webauthn', () => ({
  createPasskey: vi.fn(),
  isPasskeyCancellation: () => false,
  isPasskeySupported: () => true,
}))

/** ページが最初に引く 3 本（/me・二要素認証の状態・パスキーの一覧）を返す。 */
function respondToGet(path: string) {
  if (path === '/api/account/security/two-factor')
    return Promise.resolve({ enabled: false, enrolling: false })
  if (path === '/api/account/security/passkeys') return Promise.resolve([])
  return Promise.resolve(ME)
}

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

async function renderPage() {
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
  await waitFor(() => {
    expect(screen.getByLabelText('Email')).toHaveValue('admin@example.com')
  })
}

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockImplementation(respondToGet)
    apiPut.mockResolvedValue(ME)
    apiPost.mockResolvedValue({})
    // jsdom は matchMedia を持たない（ThemeProvider が OS の配色を見る）。
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    )
  })

  it('メールアドレスと表示名を保存すると PUT /api/auth/me が飛び、/me を引き直す', async () => {
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
    // 保存後にトーストが出て、認証状態（/me）を取り直す
    await waitFor(() => {
      expect(screen.getByText('Saved.')).toBeInTheDocument()
    })
    expect(apiGet).toHaveBeenCalledWith('/api/auth/me')
  })

  it('保存に失敗するとエラートーストを出す', async () => {
    await renderPage()
    apiPut.mockRejectedValueOnce(new Error('boom'))

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Something went wrong.')).toBeInTheDocument()
    })
  })

  it('言語・テーマの選択がこのページに出る', async () => {
    await renderPage()

    expect(screen.getByLabelText('Language')).toBeInTheDocument()
    expect(screen.getByLabelText('Theme')).toBeInTheDocument()
  })

  it('パスワード変更・二要素認証・パスキーの区画がこのページに出る', async () => {
    await renderPage()

    expect(screen.getByRole('heading', { name: 'Change password' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('Two-factor authentication is off.')).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { name: 'Passkeys' })).toBeInTheDocument()
    expect(screen.getByText('No passkeys registered yet.')).toBeInTheDocument()
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

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Set up' })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Set up' }))

    await waitFor(() => {
      expect(screen.getByAltText('Setup QR code for your authenticator app')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Verification code')).toBeInTheDocument()
  })
})
