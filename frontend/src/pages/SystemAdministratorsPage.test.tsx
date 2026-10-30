/**
 * システム管理者どうしの付け外し（ADR-0079 §1・§5）。
 *
 * 見るのは、足すと招待を送れたかを知らせること・自分の行には外すボタンを出さないこと・
 * サーバーが断った理由（最後の 1 人など）を出すこと。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type * as ApiModule from '../services/api'
import { ApiError } from '../services/api'
import { SystemAdministratorsPage } from './SystemAdministratorsPage'

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get: apiGet, post: apiPost, delete: apiDelete },
}))
vi.mock('../store/AuthContext', () => ({ useAuth: () => ({ user: { user_id: 1 } }) }))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const ADMINISTRATORS = [
  { id: 1, email: 'me@ops.example', username: 'me', is_active: true },
  { id: 2, email: 'second@ops.example', username: 'second', is_active: true },
]

async function renderPage() {
  apiGet.mockResolvedValue(ADMINISTRATORS)
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <SystemAdministratorsPage />
      </ToastProvider>
    </I18nProvider>,
  )
  await screen.findByText('second@ops.example')
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name }).closest('tr')
  if (!row) throw new Error(`${name} の行が無い`)
  return row
}

/** 入力の検査を通さずに送る（空のまま送ったときにサーバーが断る道を見る）。 */
function submitWithout(button: HTMLElement) {
  const form = button.closest('form')
  if (!form) throw new Error('フォームが無い')
  fireEvent.submit(form)
}

describe('SystemAdministratorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiDelete.mockResolvedValue(undefined)
  })

  it('自分は外せない（外すボタンを出さない）', async () => {
    await renderPage()
    expect(within(rowOf('me')).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    fireEvent.click(within(rowOf('second')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/system/administrators/2')
    })
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('外すのを断られたら理由を出す', async () => {
    apiDelete.mockRejectedValue(new ApiError(409, 'last_administrator'))
    await renderPage()
    fireEvent.click(within(rowOf('second')).getByRole('button', { name: 'Delete' }))
    expect(
      await screen.findByText('This would leave no administrator, so it was not applied.'),
    ).toBeInTheDocument()
  })

  it('足すと招待を送り、送れなければメールを整えてから足し直すよう案内する', async () => {
    apiPost.mockResolvedValue({ user_id: 3, invitation_sent: false })
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add a system administrator' }))
    const dialog = within(screen.getByRole('dialog'))
    fireEvent.change(dialog.getByLabelText('Email'), { target: { value: 'third@ops.example' } })
    fireEvent.change(dialog.getByLabelText('Display name'), { target: { value: 'third' } })
    fireEvent.click(dialog.getByRole('button', { name: 'Add' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/administrators', {
        email: 'third@ops.example',
        username: 'third',
      })
    })
    expect(await screen.findByText(/Set up mail, then add them again\./)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('同じメールアドレスの人が居れば理由を出す', async () => {
    apiPost.mockRejectedValue(new ApiError(409, 'email_already_exists'))
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add a system administrator' }))
    submitWithout(within(screen.getByRole('dialog')).getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('This email is already registered.')).toBeInTheDocument()
  })
})
