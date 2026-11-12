/**
 * Role switching (ADR-0078 §1).
 *
 * Checks three things: switching is done as "reissue the token -> refetch /me"; nothing is
 * shown to users with nothing to choose; and the opened menu can be closed.
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
  has_password: true,
  rp_logout_enabled: false,
}

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost },
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
  // Wait until /me resolves (nothing is rendered while treated as signed out).
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

  it('offers the held roles and "All roles" as options', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())

    const options = screen.getAllByRole('menuitemradio')
    expect(options).toHaveLength(3)
    expect(screen.getByRole('menuitemradio', { name: 'All roles' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'manager' })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: 'member' })).toBeInTheDocument()
    // "All roles" is selected by default
    expect(screen.getByRole('menuitemradio', { name: 'All roles' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('on select swaps the session and refetches /me', async () => {
    await renderSwitcher(MULTI_ROLE)
    // The token moves into the cookie, so the response carries only the lifetime (ADR-0076 §4).
    apiPost.mockResolvedValue({ expires_in: 900 })
    apiGet.mockResolvedValue({ ...MULTI_ROLE, active_role: 'member', scopes: ['dashboard:view'] })

    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'member' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/auth/switch-role', { role: 'member' })
    })
    await waitFor(() => {
      expect(screen.getByText('Now acting as member.')).toBeInTheDocument()
    })
    // After switching, the selected role shows on the button
    expect(screen.getByRole('button', { name: /member/ })).toBeInTheDocument()
  })

  it('reports an error and keeps the selection when switching fails', async () => {
    await renderSwitcher(MULTI_ROLE)
    apiPost.mockRejectedValue(new Error('boom'))

    fireEvent.click(toggle())
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'member' }))

    await waitFor(() => {
      expect(screen.getByText('Something went wrong.')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /All roles/ })).toBeInTheDocument()
  })

  it('closes on Esc and returns focus to the button', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())
    expect(screen.getByRole('menu')).toBeInTheDocument()

    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(toggle())
  })

  it('closes when clicking outside the menu', async () => {
    await renderSwitcher(MULTI_ROLE)

    fireEvent.click(toggle())
    act(() => {
      fireEvent.mouseDown(document.body)
    })

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('shows nothing when the user has one role or fewer', async () => {
    await renderSwitcher({ ...MULTI_ROLE, roles: ['member'] })

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
