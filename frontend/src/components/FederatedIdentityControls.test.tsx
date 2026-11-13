/**
 * IdP linking section (ADR-0077 §5).
 *
 * Checks four things: pressing navigates to the IdP; note: **the page itself navigates**
 * (the server does not return 303); no unlink is offered for a link whose removal would lock
 * the user out; and an error on the return is turned into a message.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '../i18n'
import { FederatedIdentityControls } from './FederatedIdentityControls'
import { ToastProvider } from './ToastNotification'

const { apiGet, apiPost, apiDelete, assign } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  assign: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost, delete: apiDelete },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

interface Link {
  available: boolean
  display_name: string
  linked: boolean
  linked_at: string | null
  can_unlink: boolean
}

const NOT_LINKED: Link = {
  available: true,
  display_name: 'Example IdP',
  linked: false,
  linked_at: null,
  can_unlink: false,
}

async function renderControls(link: Link, entry = '/profile/security') {
  // Note: set up responses before rendering. Replacing them later makes the first request
  //   return the default value, and the state we want to see is not rendered.
  apiGet.mockResolvedValue(link)
  render(
    <MemoryRouter initialEntries={[entry]}>
      <I18nProvider settings={SETTINGS}>
        <ToastProvider>
          <FederatedIdentityControls />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
  await waitFor(() => {
    expect(apiGet).toHaveBeenCalledWith('/api/auth/sso/link')
  })
}

describe('FederatedIdentityControls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockResolvedValue(NOT_LINKED)
    vi.stubGlobal('location', { assign })
  })

  it('does not render the section at all when SSO is unavailable', async () => {
    apiGet.mockResolvedValue({ ...NOT_LINKED, available: false })
    const { container } = render(
      <MemoryRouter>
        <I18nProvider settings={SETTINGS}>
          <ToastProvider>
            <FederatedIdentityControls />
          </ToastProvider>
        </I18nProvider>
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith('/api/auth/sso/link')
    })
    expect(container.querySelector('button')).toBeNull()
  })

  it('on press fetches the round-trip entry and the page navigates to the IdP itself', async () => {
    await renderControls(NOT_LINKED)
    apiPost.mockResolvedValue({ authorization_url: 'https://idp.example.test/authorize?state=s' })

    fireEvent.click(await screen.findByRole('button', { name: 'Link with Example IdP' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/auth/sso/link/start')
    })
    expect(assign).toHaveBeenCalledWith('https://idp.example.test/authorize?state=s')
  })

  it('shows an unlink button when linked', async () => {
    await renderControls({
      ...NOT_LINKED,
      linked: true,
      linked_at: '2026-09-14T12:00:00Z',
      can_unlink: true,
    })
    apiDelete.mockResolvedValue({ status: 'ok' })

    fireEvent.click(await screen.findByRole('button', { name: 'Unlink' }))
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/auth/sso/link')
    })
  })

  it('shows the reason instead of unlink when unlinking would lock the user out', async () => {
    await renderControls({ ...NOT_LINKED, linked: true, can_unlink: false })

    expect(
      await screen.findByText(
        'This is your only way in, so it cannot be unlinked. Set a password or add a passkey first.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Unlink' })).toBeNull()
  })

  it('turns an error on the return into a message', async () => {
    await renderControls(NOT_LINKED, '/profile/security?sso_link_error=sso_identity_taken')

    expect(
      await screen.findByText('That account is already linked to someone else.'),
    ).toBeInTheDocument()
  })
})
