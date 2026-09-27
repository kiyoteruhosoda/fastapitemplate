/**
 * IdP との連携の区画（ADR-0040）。
 *
 * 確かめるのは 4 つ ——押すと IdP へ遷移すること、⚠ **遷移するのは画面自身**
 * （サーバーは 303 を返さない）、外すと入れなくなる相手には解除を出さないこと、
 * 戻りに付いたエラーを文言に直すこと。
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
  // ⚠ 応答は描く前に決めておく。あとから差し替えると、最初の問い合わせが
  //   既定の値で返ってしまい、見たい状態が描かれない。
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

  it('SSO が使えない環境では区画そのものを出さない', async () => {
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

  it('押すと往復の入口を取り、画面が自分で IdP へ遷移する', async () => {
    await renderControls(NOT_LINKED)
    apiPost.mockResolvedValue({ authorization_url: 'https://idp.example.test/authorize?state=s' })

    fireEvent.click(await screen.findByRole('button', { name: 'Link with Example IdP' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/auth/sso/link/start')
    })
    expect(assign).toHaveBeenCalledWith('https://idp.example.test/authorize?state=s')
  })

  it('連携済みなら解除のボタンを出す', async () => {
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

  it('外すと入れなくなる相手には、解除ではなく理由を出す', async () => {
    await renderControls({ ...NOT_LINKED, linked: true, can_unlink: false })

    expect(
      await screen.findByText(
        'This is your only way in, so it cannot be unlinked. Set a password or add a passkey first.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Unlink' })).toBeNull()
  })

  it('戻りに付いたエラーを文言へ直す', async () => {
    await renderControls(NOT_LINKED, '/profile/security?sso_link_error=sso_identity_taken')

    expect(
      await screen.findByText('That account is already linked to someone else.'),
    ).toBeInTheDocument()
  })
})
