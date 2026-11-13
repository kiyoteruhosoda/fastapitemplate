/**
 * Opening and closing of the narrow-screen navigation (drawer).
 *
 * Switching the look by screen width is done by CSS (media queries in `index.css`), and jsdom
 * does not apply media queries. This only verifies that the state the media queries read -
 * the menu button's `aria-expanded` and `nav[data-open]` - changes as operated, and that all
 * the close actions work.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import type { Me } from '../store/AuthContext'
import { AuthProvider } from '../store/AuthContext'
import { ThemeProvider } from '../theme'
import { AppLayout } from './AppLayout'
import { ToastProvider } from './ToastNotification'

const ME: Me = {
  user_id: 1,
  email: 'admin@example.com',
  username: 'admin',
  scopes: ['dashboard:view', 'item:view'],
  roles: ['member'],
  active_role: null,
  has_password: true,
  rp_logout_enabled: false,
}

vi.mock('../services/api', () => ({
  api: {
    get: vi.fn(() => Promise.resolve(ME)),
    post: vi.fn(() => Promise.resolve({})),
  },
  hasTokens: () => true,
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  errorMessageKey: () => 'errors.unknown',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <I18nProvider settings={SETTINGS}>
        <ThemeProvider settings={SETTINGS}>
          <AuthProvider>
            {/* The header role switcher reports the result with a toast.
                Placed outside AppLayout, as in main.tsx. */}
            <ToastProvider>
              <AppLayout>
                <p>content</p>
              </AppLayout>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

/** The drawer opens only after sign-in, so wait for `/me` to resolve before operating. */
async function renderSignedIn() {
  renderLayout()
  await waitFor(() => {
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })
  return { nav: () => screen.getByRole('navigation', { name: 'Menu' }) }
}

function toggle() {
  return screen.getByRole('button', { name: 'Menu' })
}

function overlay() {
  return screen.getByTestId('nav-overlay')
}

function click(element: HTMLElement) {
  act(() => {
    element.click()
  })
}

describe('AppLayout navigation', () => {
  beforeEach(() => {
    // Footer reads /info. Keep it off the network.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false } as Response)),
    )
    // jsdom has no matchMedia (ThemeProvider looks at the OS color scheme).
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    )
  })

  it('is closed by default', async () => {
    const { nav } = await renderSignedIn()
    expect(nav()).toHaveAttribute('data-open', 'false')
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    // No overlay while closed (the content can be used).
    expect(screen.queryByTestId('nav-overlay')).not.toBeInTheDocument()
  })

  it('opens with the menu button and closes on a second press', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    expect(nav()).toHaveAttribute('data-open', 'true')
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')

    click(toggle())
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('closes when the overlay is tapped', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(overlay())
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('closes with the close button inside the drawer', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(screen.getByRole('button', { name: 'Close menu' }))
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('closes on Esc', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('closes when a navigation link is chosen', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    click(screen.getByRole('link', { name: 'Items' }))
    expect(nav()).toHaveAttribute('data-open', 'false')
  })

  it('moves focus to the first control in the drawer when opened', async () => {
    await renderSignedIn()

    click(toggle())
    // The first item in the drawer is the close button (so focus does not stay on the header
    // hidden under the overlay). Focus moves after waiting one frame past the render (see the
    // comment in the implementation), so wait before checking.
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Close menu' }))
    })
  })

  it('keeps Tab from leaving the drawer', async () => {
    const { nav } = await renderSignedIn()

    click(toggle())
    const focusable = [...nav().querySelectorAll<HTMLElement>('a[href], button, select')]
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    expect(first).toBeDefined()
    expect(last).toBeDefined()

    // Tab from the last wraps to the first (does not escape to the header or content).
    act(() => {
      last?.focus()
      fireEvent.keyDown(window, { key: 'Tab' })
    })
    expect(document.activeElement).toBe(first)

    // Shift+Tab from the first wraps to the last.
    act(() => {
      fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    })
    expect(document.activeElement).toBe(last)
  })

  it('returns focus to the menu button when closed', async () => {
    await renderSignedIn()

    click(toggle())
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })
    expect(document.activeElement).toBe(toggle())
  })

  it('does not move focus while closed', async () => {
    await renderSignedIn()

    const logout = screen.getByRole('button', { name: 'Logout' })
    act(() => {
      logout.focus()
    })
    expect(document.activeElement).toBe(logout)
  })

  it('hides items for scopes the user does not hold', async () => {
    const { nav } = await renderSignedIn()
    expect(nav()).toHaveAttribute('data-open', 'false')
    expect(screen.getByRole('link', { name: 'Items' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
  })
})
