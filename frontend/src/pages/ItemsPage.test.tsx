/** アイテムの画面（ページ送り ADR-0095・編集・削除）。 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { ItemsPage } from './ItemsPage'

const { apiGet, apiPost, apiPut, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost, put: apiPut, delete: apiDelete },
  errorMessageKey: () => 'error.unknown_error',
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({ hasScope: () => true }),
}))

const TIMES = { created_at: '2026-10-31T00:00:00Z', updated_at: '2026-10-31T00:00:00Z' }

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
          ? { entries: [{ id: 21, name: 'second page', ...TIMES }], total: 21 }
          : {
              entries: Array.from({ length: 20 }, (_, i) => ({
                id: i + 1,
                name: `item ${String(i + 1)}`,
                ...TIMES,
              })),
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

  it('編集すると PUT が飛び、読み直す', async () => {
    apiPut.mockResolvedValue({})
    renderPage()
    expect(await screen.findByText('item 1')).toBeInTheDocument()

    const row = screen.getByText('item 1').closest('tr')
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'renamed' } })
    apiGet.mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/items/1', { name: 'renamed' })
    })
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled()
    })
  })

  it('削除すると DELETE が飛び、読み直す', async () => {
    apiDelete.mockResolvedValue(undefined)
    renderPage()
    expect(await screen.findByText('item 1')).toBeInTheDocument()

    const row = screen.getByText('item 1').closest('tr')
    apiGet.mockClear()
    fireEvent.click(within(row as HTMLElement).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/items/1')
    })
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalled()
    })
  })
})
