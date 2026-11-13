/**
 * Shared notes (ADR-0078 §6). Checks the two stages of visibility.
 *
 * - "Write a note" is shown by scope (`note:write`)
 * - Per-row "Edit" / "Delete" are shown by the server's `can_change` (not on other people's notes,
 *   even with the scope)
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type * as ApiModule from '../services/api'
import { NotesPage } from './NotesPage'

const { apiGet, scopes } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  scopes: { granted: [] as string[] },
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get: apiGet, post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({
    hasScope: (...codes: string[]) => codes.every((c) => scopes.granted.includes(c)),
  }),
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const MINE = { id: 1, title: 'Mine', body: '', shared_group_id: null, mine: true, can_change: true }
const THEIRS = {
  id: 2,
  title: 'Theirs',
  body: 'hello',
  shared_group_id: 7,
  mine: false,
  can_change: false,
}

async function renderPage() {
  apiGet.mockImplementation((path: string) =>
    Promise.resolve(path === '/api/notes' ? [MINE, THEIRS] : [{ id: 7, name: 'Family' }]),
  )
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <NotesPage />
      </ToastProvider>
    </I18nProvider>,
  )
  await screen.findByText('Mine')
}

function rowOf(title: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name: title }).closest('tr')
  if (!row) throw new Error(`no row for ${title}`)
  return row
}

describe('NotesPage', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('shows edit and delete only on can_change rows (not on notes of others even with note:write)', async () => {
    scopes.granted = ['note:view', 'note:write']
    await renderPage()

    expect(within(rowOf('Mine')).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(within(rowOf('Mine')).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(within(rowOf('Theirs')).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(within(rowOf('Theirs')).getByRole('button', { name: 'Open' })).toBeInTheDocument()
    await waitFor(() => {
      expect(within(rowOf('Theirs')).getByText('Family')).toBeInTheDocument()
    })
  })

  it('without note:write hides the write and edit buttons and does not load share targets', async () => {
    scopes.granted = ['note:view']
    await renderPage()

    expect(screen.queryByRole('button', { name: 'Write a note' })).not.toBeInTheDocument()
    // Even your own note cannot be edited without the write feature (the API also refuses by scope)
    expect(within(rowOf('Mine')).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalledWith('/api/notes/share-targets')
  })
})
