/** アイテムの画面（ページ送り。ADR-0095）。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { ItemsPage } from './ItemsPage'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost },
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({ hasScope: () => true }),
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function renderPage() {
  render(
    <MemoryRouter>
      <I18nProvider settings={SETTINGS}>
        <ToastProvider>
          <ItemsPage />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

describe('ItemsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiGet.mockImplementation((path: string) =>
      Promise.resolve(
        path.includes('offset=20')
          ? { entries: [{ id: 21, name: 'second page' }], total: 21 }
          : {
              entries: Array.from({ length: 20 }, (_, i) => ({ id: i + 1, name: `item ${i + 1}` })),
              total: 21,
            },
      ),
    )
  })

  it('次のページへ進むと、その範囲を読み直す', async () => {
    renderPage()
    expect(await screen.findByText('item 1')).toBeInTheDocument()
    expect(screen.getByText('1–20 of 21')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => {
      expect(screen.getByText('second page')).toBeInTheDocument()
    })
    expect(apiGet).toHaveBeenLastCalledWith('/api/items?limit=20&offset=20')
    expect(screen.getByText('21–21 of 21')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })
})
