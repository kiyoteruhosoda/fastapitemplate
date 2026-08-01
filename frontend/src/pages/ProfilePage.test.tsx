/**
 * プロフィールの自己編集（メールアドレス・表示名）と表示設定の配置。
 *
 * 保存が PUT /api/auth/me に飛ぶこと、成功でトーストが出て /me を引き直すこと、
 * 言語・テーマの選択がこのページに出ることを確認する（ADR-0016）。
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

const { apiGet, apiPut } = vi.hoisted(() => ({
  apiGet: vi.fn(() => Promise.resolve(ME)),
  apiPut: vi.fn(() => Promise.resolve(ME)),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, put: apiPut },
  hasTokens: () => true,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  errorMessageKey: () => 'error.unknown_error',
}))

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
})
