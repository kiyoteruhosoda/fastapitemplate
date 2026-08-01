/**
 * ユーザー管理のロール列。
 *
 * 見るのは 2 点。ロール一覧が読めないときでも既存の割り当てを失わないこと
 * （ADR-0018）と、同じ行への続けざまの更新で片方の選択が消えないこと。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { UsersPage } from './UsersPage'

const USER = {
  id: 1,
  email: 'multi@example.com',
  username: 'multi',
  is_active: true,
  roles: ['manager'],
}

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))

vi.mock('../services/api', () => ({
  api: { get: apiGet, put: apiPut, post: vi.fn(), delete: vi.fn() },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

/** `roles` を解決するか拒否するかで、ロール一覧を読める／読めないを切り替える。 */
function mockApi(catalog: { id: number; name: string }[] | null) {
  apiGet.mockImplementation((path: string) => {
    if (path === '/api/admin/users') return Promise.resolve([USER])
    return catalog === null ? Promise.reject(new Error('forbidden')) : Promise.resolve(catalog)
  })
}

async function renderPage() {
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <UsersPage />
      </ToastProvider>
    </I18nProvider>,
  )
  await waitFor(() => {
    expect(screen.getByText('multi@example.com')).toBeInTheDocument()
  })
}

describe('UsersPage のロール列', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiPut.mockResolvedValue({})
  })

  it('ロール一覧を読めればその全ロールが列になる', async () => {
    mockApi([
      { id: 1, name: 'admin' },
      { id: 2, name: 'manager' },
    ])
    await renderPage()

    expect(screen.getByRole('checkbox', { name: 'multi: admin' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeChecked()
  })

  it('ロール一覧を読めなくても、割り当て済みのロールは消えない', async () => {
    mockApi(null)
    await renderPage()

    expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeChecked()
  })

  it('更新中の行は操作を受け付けない（古い値から差分を作らない）', async () => {
    mockApi([
      { id: 1, name: 'admin' },
      { id: 2, name: 'manager' },
    ])
    await renderPage()

    // 1 つ目の更新を保留にしたまま 2 つ目を押しても、後者は送られない。
    const first = { finish: () => undefined }
    apiPut.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        first.finish = () => {
          resolve()
          return undefined
        }
      }),
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'multi: admin' }))
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeDisabled()
    })
    fireEvent.click(screen.getByRole('checkbox', { name: 'multi: manager' }))

    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut).toHaveBeenCalledWith('/api/admin/users/1', { roles: ['manager', 'admin'] })

    first.finish()
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeEnabled()
    })
  })
})
