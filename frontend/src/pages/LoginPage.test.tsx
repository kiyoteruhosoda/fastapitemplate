/**
 * ログイン画面の入口の出し分け（ADR-0025 / ADR-0026）。
 *
 * SSO のボタンを出すか、パスワード欄を出すかは**サーバーに聞く**
 * （`GET /api/auth/sso/provider`）。設定は起動後にも変わるため、画面に焼き込まない。
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  })

  it('SSO が無効ならボタンを出さず、パスワードで入れる', async () => {
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

  it('SSO が有効ならボタンを出す（名前は IdP の呼び名）', async () => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Sign in with Nolumia' })).toBeInTheDocument()
    })
    // 併用が既定。パスワードの入口も残っている（ADR-0026）。
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('ローカルの入口が閉じているとパスワード欄もパスキーも出さない', async () => {
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

  it('問い合わせに失敗してもローカルの入口は出したままにする', async () => {
    // ここで欄を隠すと、問い合わせが落ちただけで全員が締め出される。
    fetchSsoProvider.mockRejectedValue(new Error('offline'))
    renderPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Password')).toBeInTheDocument()
    })
  })

  it('サーバー側の往復が失敗したら ?sso_error を文言にして出す', async () => {
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
})
