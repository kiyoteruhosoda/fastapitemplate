/**
 * Role columns of user management.
 *
 * Checks two things: existing assignments are not lost even when the role list cannot be read
 * (ADR-0078 §2), and rapid successive updates on the same row do not drop one of the selections.
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
  entrances: { password: true, totp: false, passkeys: 0, identity_providers: [] },
}

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))

vi.mock('../services/api', () => ({
  api: { get: apiGet, put: apiPut, post: vi.fn(), delete: vi.fn() },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

/** Switches whether the role list is readable by resolving or rejecting `roles`. */
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

describe('UsersPage role columns', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiPut.mockResolvedValue({})
  })

  it('lists the ways in (so it is visible that there are two authentication systems)', async () => {
    // Note: IdP-side multi-factor does not show here. Only the entry points this app knows
    //   about can be shown, and that is exactly what "there are two authentication systems"
    //   means (ADR-0076 §7).
    apiGet.mockImplementation((path: string) =>
      path === '/api/admin/users'
        ? Promise.resolve([
            {
              ...USER,
              entrances: {
                password: false,
                totp: false,
                passkeys: 2,
                identity_providers: ['https://idp.example.test'],
              },
            },
          ])
        : Promise.resolve([{ id: 1, name: 'manager' }]),
    )
    await renderPage()

    expect(screen.getByText('Passkey ×2 / SSO')).toBeInTheDocument()
  })

  it('makes every role a column when the role list is readable', async () => {
    mockApi([
      { id: 1, name: 'owner' },
      { id: 2, name: 'manager' },
    ])
    await renderPage()

    expect(screen.getByRole('checkbox', { name: 'multi: owner' })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeChecked()
  })

  it('keeps assigned roles even when the role list cannot be read', async () => {
    mockApi(null)
    await renderPage()

    expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeChecked()
  })

  it('rejects operations on a row being updated (no diff from stale values)', async () => {
    mockApi([
      { id: 1, name: 'owner' },
      { id: 2, name: 'manager' },
    ])
    await renderPage()

    // Pressing a second one while the first update is pending does not send the second.
    const first = { finish: () => undefined }
    apiPut.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        first.finish = () => {
          resolve()
          return undefined
        }
      }),
    )
    fireEvent.click(screen.getByRole('checkbox', { name: 'multi: owner' }))
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeDisabled()
    })
    fireEvent.click(screen.getByRole('checkbox', { name: 'multi: manager' }))

    expect(apiPut).toHaveBeenCalledTimes(1)
    expect(apiPut).toHaveBeenCalledWith('/api/admin/users/1', { roles: ['manager', 'owner'] })

    first.finish()
    await waitFor(() => {
      expect(screen.getByRole('checkbox', { name: 'multi: manager' })).toBeEnabled()
    })
  })
})
