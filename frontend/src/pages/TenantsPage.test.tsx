/**
 * テナントの管理画面（ADR-0061・ADR-0065）。システム管理者だけが使う。
 *
 * 見るのは、台帳と人数だけを並べること・登録と指名で招待を送れたかを知らせること・
 * 止めたテナントしか消せず、消すには短い名前を打ち直すこと。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import type * as ApiModule from '../services/api'
import { ApiError } from '../services/api'
import { TenantsPage } from './TenantsPage'

const { apiGet, apiPost, apiPut, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('../services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  api: { get: apiGet, post: apiPost, put: apiPut, delete: apiDelete },
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
  // 一覧を読み終えるまで待つ（空の台帳もある）
  await waitFor(() => {
    expect(apiGet).toHaveBeenCalledWith('/api/system/tenants')
  })
  if (tenants.length > 0) await screen.findByText('Acme')
}

function rowOf(name: string): HTMLElement {
  const row = screen.getByRole('rowheader', { name }).closest('tr')
  if (!row) throw new Error(`${name} の行が無い`)
  return row
}

function type(label: string | HTMLElement, value: string) {
  const input = typeof label === 'string' ? screen.getByLabelText(label) : label
  fireEvent.change(input, { target: { value } })
}

/** 入力の検査を通さずに送る（空のまま送ったときにサーバーが断る道を見る）。 */
function submitWithout(button: HTMLElement) {
  const form = button.closest('form')
  if (!form) throw new Error('フォームが無い')
  fireEvent.submit(form)
}

describe('TenantsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiPut.mockResolvedValue({})
    apiDelete.mockResolvedValue(undefined)
  })

  it('台帳と人数だけを並べる（入口・SSO の有無・有効な人 / 全員・状態）', async () => {
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

  it('登録すると、最初の管理者を指名して招待を送れたかを知らせる', async () => {
    apiPost.mockResolvedValue({ tenant: ACME, designation: { user_id: 9, invitation_sent: false } })
    await renderPage([])
    fireEvent.click(screen.getByRole('button', { name: 'Register a tenant' }))
    const dialog = within(screen.getByRole('dialog'))
    type(dialog.getByLabelText(/Short name/), 'acme')
    // 表示名の欄は、テナントの名前と管理者の名前の 2 つ（並びはこの順）
    const [tenantName, adminName] = dialog.getAllByLabelText('Display name')
    if (!tenantName || !adminName) throw new Error('表示名の欄が 2 つ無い')
    type(tenantName, 'Acme')
    type(dialog.getByLabelText("Tenant administrator's email"), 'boss@acme.example')
    type(adminName, 'boss')
    fireEvent.click(dialog.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/tenants', {
        slug: 'acme',
        display_name: 'Acme',
        // 空の連携先は「SSO を使わない」
        issuer: null,
        client_id: null,
        first_admin: { email: 'boss@acme.example', username: 'boss' },
      })
    })
    expect(await screen.findByText(/The invitation could not be sent/)).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('断られたら理由を出し、ダイアログは開いたまま', async () => {
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

  it('編集は今の値で始まり、連携先を空にすると SSO を外す', async () => {
    await renderPage()
    fireEvent.click(within(rowOf('Acme')).getByRole('button', { name: 'Edit' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByLabelText('Display name')).toHaveValue('Acme')
    expect(dialog.getByLabelText(/IdP issuer URL/)).toHaveValue('https://idp.example.test/acme')
    // 編集では短い名前も管理者も変えない
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

  it('管理者を指名し直すと、そのテナントへ招待する', async () => {
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

  it('止める・再開するを切り替える', async () => {
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

  it('消せるのは止めたテナントだけで、短い名前を打ち直すまで押せない', async () => {
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
})
