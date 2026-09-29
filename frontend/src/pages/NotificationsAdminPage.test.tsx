/**
 * お知らせの配信画面（ADR-0047）。書いた内容・出す場所・宛先がそのまま送られることと、
 * 端末への通知はサーバーが送れる設定のときだけ選べることを見る。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../components/ToastNotification'
import { I18nProvider } from '../i18n'
import { NotificationsAdminPage } from './NotificationsAdminPage'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

vi.mock('../services/api', () => ({
  api: { get: apiGet, post: apiPost },
  errorMessageKey: () => 'error.unknown_error',
}))

const SETTINGS = { languages: ['en'], default_locale: 'en', default_theme: 'light' }

function serve(pushEnabled: boolean) {
  apiGet.mockImplementation((path: string) => {
    if (path === '/api/admin/notifications') return Promise.resolve([])
    if (path === '/api/admin/notifications/audiences')
      return Promise.resolve({
        groups: [{ id: 7, name: 'Accounting', member_count: 3 }],
        users: [{ id: 2, username: 'alice', email: 'alice@example.com' }],
      })
    if (path === '/api/notifications/push')
      return Promise.resolve({ enabled: pushEnabled, public_key: null })
    return Promise.reject(new Error(path))
  })
}

function renderPage() {
  render(
    <MemoryRouter>
      <I18nProvider settings={SETTINGS}>
        <ToastProvider>
          <NotificationsAdminPage />
        </ToastProvider>
      </I18nProvider>
    </MemoryRouter>,
  )
}

describe('NotificationsAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('グループ宛てに、選んだ場所で送る', async () => {
    serve(true)
    apiPost.mockResolvedValue({ recipient_count: 3 })
    renderPage()

    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Closing' } })
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Month end' } })
    fireEvent.click(screen.getByLabelText('Top of the screen'))
    fireEvent.click(screen.getByLabelText('A group'))
    const select = await screen.findByLabelText('Group')
    await screen.findByRole('option', { name: 'Accounting (3)' })
    fireEvent.change(select, { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/admin/notifications', {
        title: 'Closing',
        body: 'Month end',
        link_url: null,
        channels: ['bell', 'banner'],
        audience: { kind: 'group', target_id: 7 },
      })
    })
    expect(await screen.findByText('Sent to 3 people.')).toBeInTheDocument()
  })

  it('送れる設定でなければ端末への通知は選べない', async () => {
    serve(false)
    renderPage()

    expect(await screen.findByText(/Device notifications are off/)).toBeInTheDocument()
    expect(screen.getByLabelText('Device notification')).toBeDisabled()
  })
})
