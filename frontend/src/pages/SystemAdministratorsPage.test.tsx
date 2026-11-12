/**
 * Adding / removing people outside tenants (operators, support staff) (ADR-0079 §1, §5, ADR-0084 §4).
 *
 * Checks that adding reports whether the invitation was sent, that your own row has no remove button,
 * and that the reason the server refused (e.g. the last one) is shown.
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
  { id: 1, email: 'me@ops.example', username: 'me', is_active: true, role: 'system-admin' },
  {
    id: 2,
    email: 'second@ops.example',
    username: 'second',
    is_active: true,
    role: 'system-support',
  },
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
  if (!row) throw new Error(`no row for ${name}`)
  return row
}

/** Submits without input validation (to exercise the server refusing an empty submission). */
function submitWithout(button: HTMLElement) {
  const form = button.closest('form')
  if (!form) throw new Error('no form')
  fireEvent.submit(form)
}

describe('SystemAdministratorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiDelete.mockResolvedValue(undefined)
  })

  it('cannot remove yourself (no remove button)', async () => {
    await renderPage()
    expect(within(rowOf('me')).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    fireEvent.click(within(rowOf('second')).getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/system/administrators/2')
    })
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('shows the reason when removal is refused', async () => {
    apiDelete.mockRejectedValue(new ApiError(409, 'last_administrator'))
    await renderPage()
    fireEvent.click(within(rowOf('second')).getByRole('button', { name: 'Delete' }))
    expect(
      await screen.findByText('This would leave no administrator, so it was not applied.'),
    ).toBeInTheDocument()
  })

  it('sends an invitation on add, and if it cannot be sent advises fixing email and adding again', async () => {
    apiPost.mockResolvedValue({ user_id: 3, invitation_sent: false })
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add an operator or support staff' }))
    const dialog = within(screen.getByRole('dialog'))
    fireEvent.change(dialog.getByLabelText('Email'), { target: { value: 'third@ops.example' } })
    fireEvent.change(dialog.getByLabelText('Display name'), { target: { value: 'third' } })
    fireEvent.click(dialog.getByRole('button', { name: 'Add' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/administrators', {
        email: 'third@ops.example',
        username: 'third',
        role: 'system-admin',
      })
    })
    expect(await screen.findByText(/Set up mail, then add them again\./)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the reason when someone with the same email address exists', async () => {
    apiPost.mockRejectedValue(new ApiError(409, 'email_already_exists'))
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add an operator or support staff' }))
    submitWithout(within(screen.getByRole('dialog')).getByRole('button', { name: 'Add' }))
    expect(await screen.findByText('This email is already registered.')).toBeInTheDocument()
  })

  it('lists the roles and lets support be chosen when adding', async () => {
    apiPost.mockResolvedValue({ user_id: 3, invitation_sent: true })
    await renderPage()
    expect(within(rowOf('second')).getByText('Support')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add an operator or support staff' }))
    const dialog = within(screen.getByRole('dialog'))
    fireEvent.change(dialog.getByLabelText('Email'), { target: { value: 'help@ops.example' } })
    fireEvent.change(dialog.getByLabelText('Display name'), { target: { value: 'help' } })
    fireEvent.change(dialog.getByLabelText('Role'), { target: { value: 'system-support' } })
    fireEvent.click(dialog.getByRole('button', { name: 'Add' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/administrators', {
        email: 'help@ops.example',
        username: 'help',
        role: 'system-support',
      })
    })
  })
})
