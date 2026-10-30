/**
 * 共有メモ（ADR-0070）。出し分けの 2 段を見る。
 *
 * - 「メモを書く」は scope（`note:write`）で出す
 * - 行ごとの「編集」「削除」はサーバーの `can_change` で出す（scope を持っていても、人のメモには出さない）
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
  if (!row) throw new Error(`${title} の行が無い`)
  return row
}

describe('NotesPage', () => {
  beforeEach(() => {
    apiGet.mockReset()
  })

  it('編集と削除は can_change の行にだけ出る（note:write を持っていても人のメモには出ない）', async () => {
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

  it('note:write が無ければ書く・編集のボタンを出さず、共有先も読まない', async () => {
    scopes.granted = ['note:view']
    await renderPage()

    expect(screen.queryByRole('button', { name: 'Write a note' })).not.toBeInTheDocument()
    // 自分のメモでも、書く機能が無ければ編集できない（API も scope で断る）
    expect(within(rowOf('Mine')).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalledWith('/api/notes/share-targets')
  })
})
