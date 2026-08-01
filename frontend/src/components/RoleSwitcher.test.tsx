/**
 * ロールの切り替え（ADR-0017）。
 *
 * 見るのは 3 点。切り替えが「トークンの再発行 → /me の引き直し」で行われること、
 * 選べる先が無い利用者には何も出さないこと、開いたメニューを閉じられること。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import type { Me } from '../store/AuthContext'
import { AuthProvider } from '../store/AuthContext'
import { RoleSwitcher } from './RoleSwitcher'
import { ToastProvider } from './ToastNotification'

const MULTI_ROLE: Me = {
  user_id: 1,
  email: 'multi@example.com',
  username: 'multi',
  scopes: ['dashboard:view', 'item:view', 'log:view'],
  roles: ['manager', 'member'],
  active_role: null,
}

const { apiGet, apiPost, setTokens } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  setTokens: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost },
  hasTokens: () => true,
  setTokens,
  clearTokens: vi.fn(),
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

async function renderSwitcher(me: Me) {
  apiGet.mockResolvedValue(me)
  render(
    <MemoryRouter>
      <I18nProvider settings={SETTINGS}>
        <AuthProvider>
          <ToastProvider>
            <RoleSwitcher />
          </ToastProvider>
        </AuthProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
  // /me が解決するまで（未サインイン扱いのあいだは何も描かれない）待つ。
  if (me.roles.length > 1) {
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /All roles/ })).toBeInTheDocument()
    })
  } else {
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith('/api/auth/me')
    })
  }
}

function toggle() {
  return screen.getByRole('button', { name: /Acting as/ })
}

describe('RoleSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('保有ロールと「すべてのロール」を選択肢に出す', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())

    const options = screen.getAllByRole('menuitemradio')
    expect(options).toHaveLength(3)
    expect(screen.getByRole('menuitemradio', { name: 'All roles' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'manager' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'member' })).toBeInTheDocument()
    // 既定は「すべてのロール」が選択済み
    expect(screen.getByRole('menuitemradio', { name: 'All roles' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('選ぶとトークンを再発行して /me を引き直す', async () => {
    await renderSwitcher(MULTI_ROLE)
    apiPost.mockResolvedValue({ access_token: 'new-access', refresh_token: 'new-refresh' })
    apiGet.mockResolvedValue({ ...MULTI_ROLE, active_role: 'member', scopes: ['dashboard:view'] })

    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'member' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/auth/switch-role', { role: 'member' })
    })
    expect(setTokens).toHaveBeenCalledWith('new-access', 'new-refresh')
    await waitFor(() => {
      expect(screen.getByText('Now acting as member.')).toBeInTheDocument()
    })
    // 切り替え後は選択中のロールがボタンに出る
    expect(screen.getByRole('button', { name: /member/ })).toBeInTheDocument()
  })

  it('切り替えに失敗するとエラーを知らせ、選択は変えない', async () => {
    await renderSwitcher(MULTI_ROLE)
    apiPost.mockRejectedValue(new Error('boom'))

    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'member' }))

    await waitFor(() => {
      expect(screen.getByText('Something went wrong.')).toBeInTheDocument()
    })
    expect(setTokens).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /All roles/ })).toBeInTheDocument()
  })

  it('Esc で閉じ、ボタンへフォーカスが戻る', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())
    expect(screen.getByRole('menu')).toBeInTheDocument()

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(toggle())
  })

  it('メニューの外側を押すと閉じる', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())
    act(() => {
      fireEvent.mouseDown(document.body)
    })

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('ロールが 1 つ以下なら何も出さない', async () => {
    await renderSwitcher({ ...MULTI_ROLE, roles: ['member'] })

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
