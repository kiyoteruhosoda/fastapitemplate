/**
 * ログイン画面の入口の出し分け（ADR-0025 / ADR-0026）。
 *
 * SSO のボタンを出すか、パスワード欄を出すかは**サーバーに聞く**
 * （`GET /api/auth/sso/provider`）。設定は起動後にも変わるため、画面に焼き込まない。
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
    // 入口の出し分けを見る試験。ボタンを押さずに入る試し（ADR-0066）は済んだことにする
    window.sessionStorage.setItem('ssoSilentTried', '1')
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

  it('問い合わせが届かないうちは入口を出さず、つながったら IdP の入口を出す', async () => {
    // リリース中はサーバーに届かない。既定の入口（パスワード欄）を出すと、サーバーが戻っても
    // IdP のボタンの無い画面に取り残される。
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

  it('IdP でサインアウトして戻ると ?signed_out を文言にして出す', async () => {
    // ⚠ 出さないと、期限切れで飛ばされたのと見分けが付かない（ADR-0033）。
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

  it.each([
    ['/login?redirect_to=%2Fitems%3Fq%3Da', '/items?q=a'],
    ['/login', '/'],
    ['/login?redirect_to=https%3A%2F%2Fevil.example%2F', '/'],
  ])('SSO の入口へ開こうとしていた画面を渡す（%s → %s。ADR-0055）', async (entry, expected) => {
    fetchSsoProvider.mockResolvedValue({
      enabled: true,
      display_name: 'Nolumia',
      local_login_enabled: true,
    })
    renderPage(entry)

    fireEvent.click(await screen.findByRole('button', { name: 'Sign in with Nolumia' }))
    expect(startSsoLogin).toHaveBeenCalledWith(expected, undefined)
  })

  it('テナントの入口では、そのテナントの IdP とパスワードの再設定へつなぐ（ADR-0064）', async () => {
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

  describe('ボタンを押さずに入る試し（ADR-0066）', () => {
    const PROVIDER = { enabled: true, display_name: 'Nolumia', local_login_enabled: true }

    beforeEach(() => {
      window.sessionStorage.clear()
      fetchSsoProvider.mockResolvedValue(PROVIDER)
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('開いたら入口を描かずに prompt=none で IdP へ送り出す（行き先は保つ）', async () => {
      renderPage('/login?redirect_to=%2Fitems')

      await waitFor(() => {
        expect(startSsoLogin).toHaveBeenCalledWith('/items', undefined, { silent: true })
      })
      expect(screen.queryByRole('button', { name: 'Sign in with Nolumia' })).not.toBeInTheDocument()
      expect(window.sessionStorage.getItem('ssoSilentTried')).toBe('1')
    })

    it('試して戻ってきたら、エラーを出さずにふつうの入口を出す', async () => {
      renderPage('/login?sso_silent=declined&redirect_to=%2Fitems')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
      expect(document.querySelector('.error')).toBeNull()
    })

    it('試して戻った画面を再読み込みしたら、もう 1 回試す（ADR-0068）', async () => {
      window.sessionStorage.setItem('ssoSilentTried', '1')
      vi.spyOn(window.performance, 'getEntriesByType').mockReturnValue([
        { type: 'reload' } as PerformanceNavigationTiming,
      ])
      renderPage('/login?sso_silent=declined&redirect_to=%2Fitems')

      await waitFor(() => {
        expect(startSsoLogin).toHaveBeenCalledWith('/items', undefined, { silent: true })
      })
    })

    it('再読み込みでも、サインアウトした後は試さない', async () => {
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

    it('このタブで一度試していたら試さない', async () => {
      window.sessionStorage.setItem('ssoSilentTried', '1')
      renderPage('/login')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('サインアウトした後は試さない', async () => {
      window.localStorage.setItem('ssoSignedOut', '1')
      renderPage('/login')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('エラーが付いているときは試さない', async () => {
      renderPage('/login?sso_error=sso_account_not_linked')

      expect(
        await screen.findByRole('button', { name: 'Sign in with Nolumia' }),
      ).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })

    it('テナントの入口では、そのテナントの IdP で試す（ADR-0064）', async () => {
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

    // ⚠ 印を書けないまま試すと、戻ってきたときに試したことが分からず行き来が止まらない
    it.each([
      [
        '書くと例外になる',
        () => {
          throw new DOMException('quota', 'QuotaExceededError')
        },
      ],
      ['書いても残らない', () => undefined],
    ])('印を書けないブラウザでは試さない（%s）', async (_case, setItem) => {
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

    it('印を読めないブラウザでも試さない', async () => {
      // 読めないのは試しの印だけにする（言語や見た目の控えは無いことにする）
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

    it('SSO が無効なら試さない', async () => {
      fetchSsoProvider.mockResolvedValue({ ...PROVIDER, enabled: false })
      renderPage('/login')

      expect(await screen.findByLabelText('Password')).toBeInTheDocument()
      expect(startSsoLogin).not.toHaveBeenCalled()
    })
  })
})
