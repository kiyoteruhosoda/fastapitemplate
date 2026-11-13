/**
 * Tenant management page (ADR-0079 §1, §5). Used only by system admins.
 *
 * Checks that only the ledger and head counts are listed, that registering and appointing report
 * whether the invitation was sent, and that only suspended tenants can be deleted, after retyping
 * the short name.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type * as ApiModule from '../services/api'
import { ApiError } from '../services/api'
import { TenantsPage } from './TenantsPage'

const { apiGet, apiPost, apiPut, apiDelete, scopes } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
  scopes: { granted: [] as string[] },
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get: apiGet, post: apiPost, put: apiPut, delete: apiDelete },
}))

vi.mock('../store/AuthContext', () => ({
  useAuth: () => ({
    hasScope: (...codes: string[]) => codes.every((c) => scopes.granted.includes(c)),
  }),
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

const ACME = {
  id: 2,
  slug: 'acme',
  display_name: 'Acme',
  issuer: 'https://idp.example.test/acme',
  client_id: 'acme-rp',
  status: 'active',
  member_count: 3,
  active_member_count: 2,
}
const SUSPENDED = {
  ...ACME,
  id: 3,
  slug: 'gone',
  display_name: 'Gone',
  issuer: null,
  client_id: null,
  status: 'suspended',
}

async function renderPage(tenants: object[] = [ACME, SUSPENDED]) {
  apiGet.mockResolvedValue(tenants)
  render(
    <I18nProvider settings={SETTINGS}>
      <ToastProvider>
        <TenantsPage />
      </ToastProvider>
    </I18nProvider>,
  )
  // Wait until the list has loaded (the ledger may be empty)
  await waitFor(() => {
    expect(apiGet).toHaveBeenCalledWith('/api/system/tenants')
  })
  if (tenants.length > 0) await screen.findByText('Acme')
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name }).closest('tr')
  if (!row) throw new Error(`no row for ${name}`)
  return row
}

function type(label: string | HTMLElement, value: string) {
  const input = typeof label === 'string' ? screen.getByLabelText(label) : label
  fireEvent.change(input, { target: { value } })
}

/** Submits without input validation (to exercise the server refusing an empty submission). */
function submitWithout(button: HTMLElement) {
  const form = button.closest('form')
  if (!form) throw new Error('no form')
  fireEvent.submit(form)
}

describe('TenantsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    scopes.granted = ['tenant:view', 'tenant:manage']
    apiPut.mockResolvedValue({})
    apiDelete.mockResolvedValue(undefined)
  })

  it('lists only the ledger and head counts (entry, SSO or not, active / all, state)', async () => {
    await renderPage()
    const acme = within(rowOf('Acme'))
    expect(acme.getByText('/t/acme/login')).toBeInTheDocument()
    expect(acme.getByText('Yes')).toBeInTheDocument()
    expect(acme.getByText('2 / 3')).toBeInTheDocument()
    expect(acme.getByText('Active')).toBeInTheDocument()
    const gone = within(rowOf('Gone'))
    expect(gone.getByText('No')).toBeInTheDocument()
    expect(gone.getByText('Suspended')).toBeInTheDocument()
  })

  it('on register appoints the first admin and reports whether the invitation was sent', async () => {
    apiPost.mockResolvedValue({ tenant: ACME, designation: { user_id: 9, invitation_sent: false } })
    await renderPage([])
    fireEvent.click(screen.getByRole('button', { name: 'Register a tenant' }))
    const dialog = within(screen.getByRole('dialog'))
    type(dialog.getByLabelText(/Short name/), 'acme')
    type(dialog.getByLabelText('Tenant name'), 'Acme')
    type(dialog.getByLabelText("Tenant administrator's email"), 'boss@acme.example')
    type(dialog.getByLabelText('Display name'), 'boss')
    fireEvent.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/tenants', {
        slug: 'acme',
        display_name: 'Acme',
        // An empty IdP means "do not use SSO"
        issuer: null,
        client_id: null,
        first_admin: { email: 'boss@acme.example', username: 'boss' },
      })
    })
    expect(await screen.findByText(/The invitation could not be sent/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('shows the reason when refused and keeps the dialog open', async () => {
    apiPost.mockRejectedValue(new ApiError(409, 'issuer_already_registered'))
    await renderPage([])
    fireEvent.click(screen.getByRole('button', { name: 'Register a tenant' }))
    const dialog = within(screen.getByRole('dialog'))
    submitWithout(dialog.getByRole('button', { name: 'Save' }))

    expect(
      await screen.findByText('That issuer is already registered to another tenant.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('starts editing with the current values, and clearing the IdP removes SSO', async () => {
    await renderPage()
    fireEvent.click(within(rowOf('Acme')).getByRole('button', { name: 'Edit' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText('Tenant name')).toHaveValue('Acme')
    expect(dialog.getByLabelText(/IdP issuer URL/)).toHaveValue('https://idp.example.test/acme')
    // Editing changes neither the short name nor the admin
    expect(dialog.queryByLabelText(/Short name/)).not.toBeInTheDocument()
    expect(dialog.queryByLabelText("Tenant administrator's email")).not.toBeInTheDocument()
    type(dialog.getByLabelText(/IdP issuer URL/), '')
    type(dialog.getByLabelText('Client ID registered at the IdP'), '')
    fireEvent.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/system/tenants/2', {
        display_name: 'Acme',
        issuer: '',
        client_id: '',
      })
    })
  })

  it('re-appointing an admin invites them to that tenant', async () => {
    apiPost.mockResolvedValue({ user_id: 10, invitation_sent: true })
    await renderPage()
    fireEvent.click(
      within(rowOf('Acme')).getByRole('button', { name: 'Designate an administrator' }),
    )
    const dialog = within(screen.getByRole('dialog'))
    type(dialog.getByLabelText("Tenant administrator's email"), 'deputy@acme.example')
    type(dialog.getByLabelText('Display name'), 'deputy')
    fireEvent.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/tenants/2/administrators', {
        email: 'deputy@acme.example',
        username: 'deputy',
      })
    })
    expect(await screen.findByText('The invitation was sent.')).toBeInTheDocument()
  })

  it('toggles suspend and resume', async () => {
    await renderPage()
    fireEvent.click(within(rowOf('Acme')).getByRole('button', { name: 'Suspend' }))
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/system/tenants/2', { status: 'suspended' })
    })
    fireEvent.click(within(rowOf('Gone')).getByRole('button', { name: 'Resume' }))
    await waitFor(() => {
      expect(apiPut).toHaveBeenCalledWith('/api/system/tenants/3', { status: 'active' })
    })
  })

  it('deletes only suspended tenants, disabled until the short name is retyped', async () => {
    await renderPage()
    expect(within(rowOf('Acme')).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()

    fireEvent.click(within(rowOf('Gone')).getByRole('button', { name: 'Delete' }))
    const dialog = within(screen.getByRole('dialog'))
    const confirm = dialog.getByRole('button', { name: 'Delete' })
    expect(confirm).toBeDisabled()
    type(dialog.getByLabelText('Type the short name to confirm'), 'Gone')
    expect(confirm).toBeDisabled()
    type(dialog.getByLabelText('Type the short name to confirm'), 'gone')
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/system/tenants/3')
    })
  })

  it('with only tenant:view (support) shows just the list without change buttons', async () => {
    scopes.granted = ['tenant:view']
    await renderPage()
    expect(within(rowOf('Acme')).getByText('/t/acme/login')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Register a tenant' })).not.toBeInTheDocument()
    expect(within(rowOf('Acme')).queryAllByRole('button')).toHaveLength(0)
  })
})
